import asyncio
import os
import time as time_module
import uuid

import httpx
import pytest

from datetime import time

from app.main import is_closing_time


ORCHESTRATOR_URL = os.getenv(
    "ORCHESTRATOR_URL",
    "http://orchestrator:8000"
)

CONTABLE_URL = os.getenv(
    "CONTABLE_URL",
    "http://contable:8001"
)

GESTION_URL = os.getenv(
    "GESTION_URL",
    "http://gestion:8002"
)

LEALTAD_URL = os.getenv(
    "LEALTAD_URL",
    "http://lealtad:8003"
)


def crear_venta(
    id_venta: str
) -> dict:

    return {
        "id_venta": id_venta,
        "id_cliente": "CLI-TEST",
        "items": [
            {
                "sku": "SKU-TEST",
                "descripcion": "Producto prueba",
                "cantidad": 1,
                "precio_unitario": 10.0
            }
        ],
        "total": 10.0,
        "canal": "ecommerce",
        "timestamp": (
            "2026-08-17T01:00:00-05:00"
        )
    }


def esperar_intentos(
    sistema_url: str,
    id_venta: str,
    minimo: int,
    timeout: int = 15
) -> int:

    inicio = time_module.time()

    while (
        time_module.time() - inicio
        < timeout
    ):

        try:
            response = httpx.get(
                (
                    f"{sistema_url}"
                    f"/debug/intentos/"
                    f"{id_venta}"
                ),
                timeout=3
            )

            if response.status_code == 200:

                intentos = response.json()[
                    "intentos"
                ]

                if intentos >= minimo:
                    return intentos

        except httpx.HTTPError:
            pass

        time_module.sleep(0.5)

    raise AssertionError(
        f"No se alcanzaron "
        f"{minimo} intentos para "
        f"{id_venta}"
    )


# =========================================================
# TEST 1
# Venta procesada exitosamente
# =========================================================

def test_venta_procesada_exitosamente():

    id_venta = (
        "V-TEST-OK-"
        + uuid.uuid4().hex[:8]
    )

    venta = crear_venta(
        id_venta
    )

    response = httpx.post(
        f"{ORCHESTRATOR_URL}/ventas",
        json=venta,
        timeout=5
    )

    assert response.status_code == 202

    data = response.json()

    assert data["id_venta"] == id_venta
    assert data["estado"] == "ENCOLADO"

    # Verificamos que realmente llegó
    # al Sistema Contable.

    intentos_contable = esperar_intentos(
        CONTABLE_URL,
        id_venta,
        1
    )

    assert intentos_contable == 1

    # Gestión recibió la factura.

    intentos_gestion = esperar_intentos(
        GESTION_URL,
        id_venta,
        1
    )

    assert intentos_gestion == 1

    # Lealtad recibió notificación.

    intentos_lealtad = esperar_intentos(
        LEALTAD_URL,
        id_venta,
        1
    )

    assert intentos_lealtad == 1


# =========================================================
# TEST 2
# Venta recibida durante cierre nocturno
# =========================================================

def test_horario_cierre():

    assert is_closing_time(
        time(22, 0)
    ) is True

    assert is_closing_time(
        time(22, 30)
    ) is True

    assert is_closing_time(
        time(23, 59)
    ) is True

    assert is_closing_time(
        time(21, 59)
    ) is False

    assert is_closing_time(
        time(0, 0)
    ) is False


# =========================================================
# TEST 3
# Fallo Contable + reintento
# =========================================================

def test_fallo_contable_con_reintento():

    id_venta = (
        "V-FAIL-RETRY-"
        + uuid.uuid4().hex[:8]
    )

    response = httpx.post(
        f"{ORCHESTRATOR_URL}/ventas",
        json=crear_venta(id_venta),
        timeout=5
    )

    assert response.status_code == 202

    intentos = esperar_intentos(
        CONTABLE_URL,
        id_venta,
        3
    )

    # Dos fallos + tercer intento exitoso.
    assert intentos == 3

    # Después de emitir la factura,
    # Gestión también debe recibirla.

    assert esperar_intentos(
        GESTION_URL,
        id_venta,
        1
    ) >= 1


# =========================================================
# TEST 4
# Fallo Gestión sin duplicar factura
# =========================================================

def test_fallo_gestion_sin_duplicar_factura():

    id_venta = (
        "V-FAIL-GESTION-"
        + uuid.uuid4().hex[:8]
    )

    response = httpx.post(
        f"{ORCHESTRATOR_URL}/ventas",
        json=crear_venta(id_venta),
        timeout=5
    )

    assert response.status_code == 202

    # Gestión debe recibir 3 intentos:
    # fallo, fallo, éxito.

    intentos_gestion = esperar_intentos(
        GESTION_URL,
        id_venta,
        3
    )

    assert intentos_gestion == 3

    # Esta es la comprobación crítica:
    # Contable solo debe haber recibido
    # UNA solicitud de factura.

    intentos_contable = esperar_intentos(
        CONTABLE_URL,
        id_venta,
        1
    )

    assert intentos_contable == 1


# =========================================================
# TEST 5
# Payload inválido → HTTP 400
# =========================================================

def test_payload_invalido():

    payload = {
        "id_venta": "V-INVALIDA",
        "id_cliente": "CLI-TEST",
        "items": [],
        "total": 10,
        "canal": "CANAL_INVALIDO"
    }

    response = httpx.post(
        f"{ORCHESTRATOR_URL}/ventas",
        json=payload,
        timeout=5
    )

    assert response.status_code == 400

    data = response.json()

    assert data["error"] == (
        "Payload inválido"
    )