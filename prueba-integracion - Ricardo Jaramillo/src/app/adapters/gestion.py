import httpx

from app.models.schemas import FacturaResponse, Venta


class GestionError(Exception):
    pass


class GestionAdapter:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def notificar_factura(
        self,
        venta: Venta,
        factura: FacturaResponse
    ) -> dict:

        url = f"{self.base_url}/facturas/confirmacion"

        payload = {
            "id_venta": venta.id_venta,
            "id_cliente": venta.id_cliente,
            "id_factura": factura.id_factura,
            "estado": factura.estado,
            "timestamp_emision": (
                factura.timestamp_emision.isoformat()
                if factura.timestamp_emision
                else None
            )
        }

        try:
            async with httpx.AsyncClient(
                timeout=10.0
            ) as client:

                response = await client.post(
                    url,
                    json=payload
                )

            response.raise_for_status()

            return response.json()

        except httpx.HTTPError as error:

            raise GestionError(
                f"Error notificando al "
                f"Sistema de Gestión: {error}"
            ) from error