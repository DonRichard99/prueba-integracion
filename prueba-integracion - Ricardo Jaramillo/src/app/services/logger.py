import json

from datetime import datetime
from zoneinfo import ZoneInfo


def log_event(
    id_venta: str,
    sistema_destino: str,
    estado: str,
    detalle_error: str | None = None
):
    registro = {
        "timestamp": (
            datetime.now(
                ZoneInfo(
                    "America/Guayaquil"
                )
            ).isoformat()
        ),
        "id_venta": id_venta,
        "sistema_destino": sistema_destino,
        "estado": estado,
        "detalle_error": detalle_error
    }

    print(
        json.dumps(
            registro,
            ensure_ascii=False
        )
    )