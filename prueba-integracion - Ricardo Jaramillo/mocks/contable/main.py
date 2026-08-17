from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI(
    title="Mock Sistema Contable"
)


# Guarda cuántos intentos ha recibido cada venta.
intentos_por_venta: dict[str, int] = {}


class FacturaRequest(BaseModel):
    id_venta: str
    id_cliente: str
    items: list
    total: float
    canal: str
    timestamp: datetime


@app.get("/health")
async def health():
    return {
        "status": "OK",
        "service": "contable"
    }


@app.get("/debug/intentos/{id_venta}")
async def obtener_intentos(id_venta: str):
    return {
        "id_venta": id_venta,
        "intentos": intentos_por_venta.get(
            id_venta,
            0
        )
    }


@app.post("/facturas")
async def emitir_factura(
    venta: FacturaRequest
):

    intentos = intentos_por_venta.get(
        venta.id_venta,
        0
    )

    intentos_por_venta[
        venta.id_venta
    ] = intentos + 1

    print(
        f"[CONTABLE] Solicitud recibida "
        f"para venta {venta.id_venta}. "
        f"Intento {intentos + 1}"
    )

    # -----------------------------------------------------
    # FALLO TEMPORAL
    #
    # Cualquier ID que empiece por:
    #
    # V-FAIL-RETRY
    #
    # falla los dos primeros intentos
    # y funciona correctamente en el tercero.
    # -----------------------------------------------------

    if (
        venta.id_venta.startswith(
            "V-FAIL-RETRY"
        )
        and intentos < 2
    ):

        print(
            f"[CONTABLE] Simulando fallo "
            f"temporal para "
            f"{venta.id_venta}"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Sistema Contable "
                "temporalmente no disponible"
            )
        )

    # -----------------------------------------------------
    # FALLO PERMANENTE
    #
    # Se utiliza para comprobar DLQ.
    # -----------------------------------------------------

    if venta.id_venta.startswith(
        "V-FAIL-ALWAYS"
    ):

        print(
            f"[CONTABLE] Simulando fallo "
            f"permanente para "
            f"{venta.id_venta}"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Sistema Contable "
                "no disponible"
            )
        )

    # -----------------------------------------------------
    # EMISIÓN NORMAL
    # -----------------------------------------------------

    id_factura = (
        f"FAC-{venta.id_venta}"
    )

    timestamp_emision = datetime.now(
        timezone.utc
    ).isoformat()

    print(
        f"[CONTABLE] Factura emitida: "
        f"{id_factura}"
    )

    return {
        "id_factura": id_factura,
        "id_venta": venta.id_venta,
        "estado": "Factura Emitida",
        "timestamp_emision": timestamp_emision
    }