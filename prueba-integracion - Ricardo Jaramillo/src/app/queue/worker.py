import asyncio
import json
import os

from datetime import datetime, time
from zoneinfo import ZoneInfo

import aio_pika

from app.adapters.contable import (
    ContableAdapter,
    ContableError,
)
from app.adapters.gestion import (
    GestionAdapter,
    GestionError,
)
from app.adapters.lealtad import LealtadAdapter

from app.models.schemas import (
    Venta,
    FacturaResponse,
)

from app.services.logger import log_event


# =========================================================
# CONFIGURACIÓN DE COLAS
# =========================================================

QUEUE_NAME = "facturacion"
DLQ_NAME = "facturacion_dlq"


# =========================================================
# IDEMPOTENCIA
# =========================================================
# Para el PoC se almacena en memoria:
#
# id_venta -> factura
#
# Si la misma venta vuelve a procesarse después de haber
# emitido una factura, no se vuelve a llamar a Contable.
# =========================================================

facturas_emitidas: dict[str, dict] = {}


# =========================================================
# UTILIDADES DE HORARIO
# =========================================================

def parse_time(value: str) -> time:
    hours, minutes = map(
        int,
        value.split(":")
    )

    return time(
        hours,
        minutes
    )


def is_closing_time() -> bool:

    closing_start = parse_time(
        os.getenv(
            "CLOSING_START",
            "22:00"
        )
    )

    closing_end = parse_time(
        os.getenv(
            "CLOSING_END",
            "23:59"
        )
    )

    now = datetime.now(
        ZoneInfo("America/Guayaquil")
    ).time()

    return (
        closing_start
        <= now
        <= closing_end
    )


# =========================================================
# CONEXIÓN ROBUSTA CON RABBITMQ
# =========================================================

async def connect_to_rabbitmq(
    rabbitmq_url: str
):

    attempt = 1

    while True:

        try:

            print(
                f"[WORKER] Conectando a RabbitMQ "
                f"(intento {attempt})..."
            )

            connection = (
                await aio_pika.connect_robust(
                    rabbitmq_url
                )
            )

            print(
                "[WORKER] Conexión con "
                "RabbitMQ establecida"
            )

            return connection

        except Exception as error:

            print(
                f"[WORKER] RabbitMQ "
                f"no disponible: {error}"
            )

            await asyncio.sleep(5)

            attempt += 1


# =========================================================
# REINTENTOS CONTRA SISTEMA CONTABLE
# =========================================================

async def emitir_factura_con_reintento(
    contable: ContableAdapter,
    venta: Venta
) -> FacturaResponse:

    retry_max = int(
        os.getenv(
            "RETRY_MAX",
            "3"
        )
    )

    retry_base = float(
        os.getenv(
            "RETRY_BASE_SECONDS",
            "1"
        )
    )

    for intento in range(
        1,
        retry_max + 1
    ):

        try:

            print(
                f"[WORKER] Intento "
                f"{intento}/{retry_max} "
                f"para venta "
                f"{venta.id_venta}"
            )

            factura = (
                await contable.emitir_factura(
                    venta
                )
            )

            return factura

        except ContableError as error:

            print(
                f"[WORKER] Fallo contable "
                f"en intento {intento}: "
                f"{error}"
            )

            if intento == retry_max:

                print(
                    "[WORKER] Se agotaron "
                    "los reintentos contra "
                    "Sistema Contable"
                )

                raise

            # Backoff exponencial:
            # intento 1 -> 1 segundo
            # intento 2 -> 2 segundos

            espera = (
                retry_base
                * (2 ** (intento - 1))
            )

            print(
                f"[WORKER] Reintentando "
                f"en {espera} segundos..."
            )

            await asyncio.sleep(
                espera
            )


# =========================================================
# REINTENTOS GENÉRICOS
# GESTIÓN Y LEALTAD
# =========================================================

async def ejecutar_con_reintento(
    nombre_sistema: str,
    operacion,
    venta: Venta
):

    retry_max = int(
        os.getenv(
            "RETRY_MAX",
            "3"
        )
    )

    retry_base = float(
        os.getenv(
            "RETRY_BASE_SECONDS",
            "1"
        )
    )

    ultimo_error = None

    for intento in range(
        1,
        retry_max + 1
    ):

        try:

            print(
                f"[WORKER] "
                f"{nombre_sistema} "
                f"intento "
                f"{intento}/{retry_max} "
                f"para venta "
                f"{venta.id_venta}"
            )

            return await operacion()

        except Exception as error:

            ultimo_error = error

            print(
                f"[WORKER] Fallo en "
                f"{nombre_sistema}, "
                f"intento {intento}: "
                f"{error}"
            )

            if intento == retry_max:
                break

            espera = (
                retry_base
                * (2 ** (intento - 1))
            )

            print(
                f"[WORKER] Reintentando "
                f"{nombre_sistema} "
                f"en {espera} segundos..."
            )

            await asyncio.sleep(
                espera
            )

    raise ultimo_error


# =========================================================
# DEAD LETTER QUEUE
# =========================================================

async def enviar_a_dlq(
    message: aio_pika.IncomingMessage,
    error: str
):

    rabbitmq_url = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@rabbitmq:5672/"
    )

    connection = (
        await connect_to_rabbitmq(
            rabbitmq_url
        )
    )

    try:

        channel = await connection.channel()

        dlq = await channel.declare_queue(
            DLQ_NAME,
            durable=True
        )

        data = json.loads(
            message.body.decode()
        )

        data["estado"] = "FALLIDO"

        data["detalle_error"] = error

        data["timestamp_fallo"] = (
            datetime.now(
                ZoneInfo(
                    "America/Guayaquil"
                )
            ).isoformat()
        )

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(
                    data
                ).encode(),
                delivery_mode=(
                    aio_pika
                    .DeliveryMode
                    .PERSISTENT
                )
            ),
            routing_key=dlq.name
        )

        print(
            f"[WORKER] Venta "
            f"{data.get('id_venta')} "
            f"enviada a DLQ"
        )

    finally:

        await connection.close()


# =========================================================
# PROCESAMIENTO PRINCIPAL
# =========================================================

async def process_message(
    message: aio_pika.IncomingMessage
):

    venta = None

    try:

        # -------------------------------------------------
        # 1. Leer mensaje
        # -------------------------------------------------

        data = json.loads(
            message.body.decode()
        )

        # -------------------------------------------------
        # 2. Validar venta
        # -------------------------------------------------

        venta = Venta.model_validate(
            data
        )

        print(
            f"[WORKER] Mensaje recibido "
            f"para venta "
            f"{venta.id_venta}"
        )

        # -------------------------------------------------
        # 3. CIERRE CONTABLE
        # -------------------------------------------------

        if is_closing_time():

            print(
                f"[WORKER] Cierre contable "
                f"activo. Venta "
                f"{venta.id_venta} "
                f"permanece en cola."
            )

            log_event(
                venta.id_venta,
                "SISTEMA_CONTABLE",
                "ENCOLADO",
                "Cierre contable activo"
            )

            await message.nack(
                requeue=True
            )

            # Evita que el Worker haga un ciclo
            # excesivamente rápido durante el cierre.
            await asyncio.sleep(10)

            return

        print(
            f"[WORKER] Procesando venta: "
            f"{venta.id_venta}"
        )

        # -------------------------------------------------
        # 4. URLs
        # -------------------------------------------------

        contable_url = os.getenv(
            "CONTABLE_URL",
            "http://contable:8001"
        )

        gestion_url = os.getenv(
            "GESTION_URL",
            "http://gestion:8002"
        )

        lealtad_url = os.getenv(
            "LEALTAD_URL",
            "http://lealtad:8003"
        )

        # -------------------------------------------------
        # 5. SISTEMA CONTABLE + IDEMPOTENCIA
        # -------------------------------------------------

        contable = ContableAdapter(
            contable_url
        )

        if (
            venta.id_venta
            in facturas_emitidas
        ):

            print(
                f"[WORKER] Venta "
                f"{venta.id_venta} "
                f"ya posee factura. "
                f"No se vuelve a emitir."
            )

            factura = (
                FacturaResponse.model_validate(
                    facturas_emitidas[
                        venta.id_venta
                    ]
                )
            )

        else:

            factura = (
                await emitir_factura_con_reintento(
                    contable,
                    venta
                )
            )

            # Guardamos la factura inmediatamente
            # después de emitirla.
            #
            # Si Gestión o Lealtad fallan posteriormente,
            # la factura no debe volver a emitirse.

            facturas_emitidas[
                venta.id_venta
            ] = factura.model_dump(
                mode="json"
            )

            print(
                f"[WORKER] Factura registrada "
                f"para idempotencia: "
                f"{factura.id_factura}"
            )

        print(
            f"[WORKER] Factura disponible: "
            f"{factura.id_factura}"
        )

        # Logging estructurado de Contable.

        log_event(
            venta.id_venta,
            "SISTEMA_CONTABLE",
            "OK"
        )

        # -------------------------------------------------
        # 6. NOTIFICAR A GESTIÓN
        # -------------------------------------------------

        gestion = GestionAdapter(
            gestion_url
        )

        resultado_gestion = (
            await ejecutar_con_reintento(
                "GESTION",
                lambda: gestion.notificar_factura(
                    venta,
                    factura
                ),
                venta
            )
        )

        print(
            f"[WORKER] Gestión: "
            f"{resultado_gestion.get('estado')}"
        )

        log_event(
            venta.id_venta,
            "SISTEMA_GESTION",
            "OK"
        )

        # -------------------------------------------------
        # 7. NOTIFICAR A LEALTAD
        # -------------------------------------------------
        #
        # Solamente se acreditan puntos si la factura
        # fue emitida correctamente.
        # -------------------------------------------------

        if (
            factura.estado
            == "Factura Emitida"
        ):

            lealtad = LealtadAdapter(
                lealtad_url
            )

            resultado_lealtad = (
                await ejecutar_con_reintento(
                    "LEALTAD",
                    lambda: lealtad.acreditar_puntos(
                        venta,
                        factura
                    ),
                    venta
                )
            )

            print(
                f"[WORKER] Lealtad: "
                f"{resultado_lealtad.estado}"
            )

            log_event(
                venta.id_venta,
                "SISTEMA_LEALTAD",
                "OK"
            )

        # -------------------------------------------------
        # 8. CONFIRMAR MENSAJE
        # -------------------------------------------------

        await message.ack()

        print(
            f"[WORKER] Venta "
            f"{venta.id_venta} "
            f"procesada correctamente"
        )

    # =====================================================
    # ERROR DE GESTIÓN
    # =====================================================

    except GestionError as error:

        if venta is not None:

            log_event(
                venta.id_venta,
                "SISTEMA_GESTION",
                "FALLIDO",
                str(error)
            )

        print(
            f"[WORKER] Error notificando "
            f"a Gestión: {error}"
        )

        print(
            "[WORKER] El mensaje será "
            "reencolado. La factura "
            "NO será duplicada gracias "
            "a la idempotencia."
        )

        await message.nack(
            requeue=True
        )

    # =====================================================
    # ERROR DEFINITIVO DE CONTABLE
    # =====================================================

    except ContableError as error:

        if venta is not None:

            log_event(
                venta.id_venta,
                "SISTEMA_CONTABLE",
                "FALLIDO",
                str(error)
            )

        print(
            f"[WORKER] Error definitivo "
            f"en Sistema Contable: "
            f"{error}"
        )

        print(
            "[WORKER] Reintentos agotados. "
            "La venta será enviada a DLQ."
        )

        try:

            await enviar_a_dlq(
                message,
                str(error)
            )

            # Ya está conservada en DLQ.
            # Confirmamos el mensaje original.

            await message.ack()

        except Exception as dlq_error:

            print(
                f"[WORKER] Error enviando "
                f"mensaje a DLQ: "
                f"{dlq_error}"
            )

            await message.nack(
                requeue=True
            )

    # =====================================================
    # ERROR GENERAL
    #
    # Aquí también caerían, por ejemplo, los fallos
    # definitivos de Lealtad.
    # =====================================================

    except Exception as error:

        if venta is not None:

            log_event(
                venta.id_venta,
                "PROCESAMIENTO",
                "FALLIDO",
                str(error)
            )

        print(
            f"[WORKER] Error procesando "
            f"mensaje: {error}"
        )

        await message.nack(
            requeue=True
        )


# =========================================================
# INICIO DEL WORKER
# =========================================================

async def start_worker():

    rabbitmq_url = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@rabbitmq:5672/"
    )

    connection = (
        await connect_to_rabbitmq(
            rabbitmq_url
        )
    )

    channel = await connection.channel()

    # Procesamiento secuencial.
    await channel.set_qos(
        prefetch_count=1
    )

    # Cola principal.
    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True
    )

    # Cola de mensajes fallidos.
    await channel.declare_queue(
        DLQ_NAME,
        durable=True
    )

    print(
        f"[WORKER] Esperando mensajes "
        f"en '{QUEUE_NAME}'"
    )

    print(
        f"[WORKER] DLQ disponible: "
        f"'{DLQ_NAME}'"
    )

    await queue.consume(
        process_message
    )

    # Mantener Worker ejecutándose.
    await asyncio.Future()