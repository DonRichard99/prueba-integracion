import os

from datetime import datetime, time
from zoneinfo import ZoneInfo
from app.adapters.lealtad import LealtadAdapter
from app.queue.rabbitmq import publish_message
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.adapters.contable import ContableAdapter
from app.models.schemas import Venta


app = FastAPI(
    title="Capa de Integración - Facturación",
    version="1.0.0"
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    return JSONResponse(
        status_code=400,
        content={
            "error": "Payload inválido",
            "detalles": exc.errors()
        }
    )


@app.get("/health")
async def health():
    return {
        "status": "OK",
        "service": "orchestrator"
    }


@app.post("/ventas", status_code=202)
async def crear_venta(venta: Venta):

    await publish_message(
        venta.model_dump(mode="json")
    )

    if is_closing_time():

        return {
            "id_venta": venta.id_venta,
            "estado": "ENCOLADO",
            "motivo": "CIERRE_CONTABLE",
            "mensaje": (
                "Venta encolada durante "
                "el cierre contable"
            )
        }

    return {
        "id_venta": venta.id_venta,
        "estado": "ENCOLADO",
        "mensaje": (
            "Venta recibida. "
            "Será procesada inmediatamente."
        )
    }
        
def parse_time(value: str) -> time:
    hours, minutes = map(int, value.split(":"))
    return time(hours, minutes)


def is_closing_time(
    current_time: time | None = None
) -> bool:

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

    if current_time is None:
        current_time = datetime.now(
            ZoneInfo("America/Guayaquil")
        ).time()

    return (
        closing_start
        <= current_time
        <= closing_end
    )