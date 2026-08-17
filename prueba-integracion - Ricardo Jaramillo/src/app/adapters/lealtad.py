import httpx

from app.models.schemas import FacturaResponse, LealtadResponse, Venta


class LealtadAdapter:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def acreditar_puntos(
        self,
        venta: Venta,
        factura: FacturaResponse
    ) -> LealtadResponse:

        if factura.estado != "Factura Emitida":
            raise ValueError(
                "No se pueden acreditar puntos sin factura emitida"
            )

        url = f"{self.base_url}/puntos"

        payload = {
            "id_venta": venta.id_venta,
            "id_cliente": venta.id_cliente,
            "id_factura": factura.id_factura,
            "estado_factura": factura.estado,
            "total": venta.total
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload
            )

        response.raise_for_status()

        return LealtadResponse.model_validate(response.json())