import os

import httpx

from fastapi import (
    FastAPI,
    HTTPException
)

from pydantic import BaseModel


app = FastAPI(
    title="Mock Sistema de Gestión"
)


# Guarda cuántas veces se intentó confirmar
# una factura para cada venta.
intentos_confirmacion: dict[str, int] = {}


class VentaRequest(BaseModel):
    id_venta: str
    id_cliente: str
    items: list
    total: float
    canal: str
    timestamp: str


class FacturaConfirmacion(BaseModel):
    id_venta: str
    id_cliente: str
    id_factura: str
    estado: str
    timestamp_emision: str | None = None


@app.get("/health")
async def health():
    return {
        "status": "OK",
        "service": "gestion"
    }


@app.get("/debug/intentos/{id_venta}")
async def obtener_intentos(id_venta: str):
    return {
        "id_venta": id_venta,
        "intentos": intentos_confirmacion.get(
            id_venta,
            0
        )
    }


# =========================================================
# WEBHOOK HACIA EL ORQUESTADOR
# =========================================================

@app.post("/webhook")
async def enviar_webhook(
    venta: VentaRequest
):

    orchestrator_url = os.getenv(
        "ORCHESTRATOR_URL",
        "http://orchestrator:8000"
    )

    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.post(
                f"{orchestrator_url}/ventas",
                json=venta.model_dump()
            )

        return {
            "webhook": "enviado",
            "status_code": response.status_code,
            "respuesta_orquestador": (
                response.json()
            )
        }

    except httpx.HTTPError as error:

        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible enviar "
                "el webhook al orquestador: "
                f"{error}"
            )
        )


# =========================================================
# CONFIRMACIÓN DE FACTURA
# =========================================================

@app.post("/facturas/confirmacion")
async def recibir_factura(
    confirmacion: FacturaConfirmacion
):

    intentos = (
        intentos_confirmacion.get(
            confirmacion.id_venta,
            0
        )
    )

    intentos_confirmacion[
        confirmacion.id_venta
    ] = intentos + 1

    print(
        f"[GESTION] Confirmación recibida "
        f"para venta "
        f"{confirmacion.id_venta}. "
        f"Intento {intentos + 1}"
    )

    # -----------------------------------------------------
    # FALLO TEMPORAL
    #
    # Cualquier ID que empiece por:
    #
    # V-FAIL-GESTION
    #
    # falla los dos primeros intentos.
    # -----------------------------------------------------

    if (
        confirmacion.id_venta.startswith(
            "V-FAIL-GESTION"
        )
        and intentos < 2
    ):

        print(
            f"[GESTION] Simulando fallo "
            f"temporal para "
            f"{confirmacion.id_venta}"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Sistema de Gestión "
                "temporalmente no disponible"
            )
        )

    # -----------------------------------------------------
    # ACTUALIZACIÓN NORMAL
    # -----------------------------------------------------

    print(
        f"[GESTION] Factura "
        f"{confirmacion.id_factura} "
        f"actualizada correctamente "
        f"para venta "
        f"{confirmacion.id_venta}"
    )

    return {
        "estado": "ACTUALIZADO",
        "id_venta": confirmacion.id_venta,
        "id_factura": confirmacion.id_factura
    }