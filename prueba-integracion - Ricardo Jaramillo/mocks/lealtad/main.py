from fastapi import (
    FastAPI,
    HTTPException
)

from pydantic import BaseModel


app = FastAPI(
    title="Mock Sistema de Lealtad"
)


# Guarda cuántas veces se intentó
# acreditar puntos para cada venta.
intentos_puntos: dict[str, int] = {}


class PuntosRequest(BaseModel):
    id_venta: str
    id_cliente: str
    id_factura: str
    estado_factura: str
    total: float


@app.get("/health")
async def health():
    return {
        "status": "OK",
        "service": "lealtad"
    }


@app.get("/debug/intentos/{id_venta}")
async def obtener_intentos(id_venta: str):
    return {
        "id_venta": id_venta,
        "intentos": intentos_puntos.get(
            id_venta,
            0
        )
    }


@app.post("/puntos")
async def acreditar_puntos(
    request: PuntosRequest
):

    intentos = intentos_puntos.get(
        request.id_venta,
        0
    )

    intentos_puntos[
        request.id_venta
    ] = intentos + 1

    print(
        f"[LEALTAD] Solicitud de puntos "
        f"para venta "
        f"{request.id_venta}. "
        f"Intento {intentos + 1}"
    )

    # -----------------------------------------------------
    # REGLA DE NEGOCIO
    #
    # No se acreditan puntos si la factura
    # todavía no está emitida.
    # -----------------------------------------------------

    if (
        request.estado_factura
        != "Factura Emitida"
    ):

        print(
            f"[LEALTAD] Acreditación "
            f"rechazada para "
            f"{request.id_venta}: "
            f"factura no emitida"
        )

        raise HTTPException(
            status_code=409,
            detail=(
                "No se pueden acreditar "
                "puntos sin una factura "
                "emitida"
            )
        )

    # -----------------------------------------------------
    # FALLO TEMPORAL
    #
    # Cualquier ID que empiece por:
    #
    # V-FAIL-LEALTAD
    #
    # falla los primeros dos intentos.
    # -----------------------------------------------------

    if (
        request.id_venta.startswith(
            "V-FAIL-LEALTAD"
        )
        and intentos < 2
    ):

        print(
            f"[LEALTAD] Simulando fallo "
            f"temporal para "
            f"{request.id_venta}"
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Sistema de Lealtad "
                "temporalmente no disponible"
            )
        )

    # -----------------------------------------------------
    # ACREDITACIÓN NORMAL
    # -----------------------------------------------------

    puntos = int(
        request.total
    )

    print(
        f"[LEALTAD] Puntos acreditados "
        f"para venta "
        f"{request.id_venta}: "
        f"{puntos}"
    )

    return {
        "id_venta": request.id_venta,
        "id_cliente": request.id_cliente,
        "estado": "Puntos Acreditados",
        "puntos": puntos
    }