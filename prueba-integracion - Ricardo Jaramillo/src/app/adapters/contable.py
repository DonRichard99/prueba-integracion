import httpx

from app.models.schemas import FacturaResponse, Venta


class ContableError(Exception):
    pass


class ContableAdapter:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def emitir_factura(
        self,
        venta: Venta
    ) -> FacturaResponse:

        url = f"{self.base_url}/facturas"

        try:
            async with httpx.AsyncClient(
                timeout=10.0
            ) as client:

                response = await client.post(
                    url,
                    json=venta.model_dump(
                        mode="json"
                    )
                )

            response.raise_for_status()

            return FacturaResponse.model_validate(
                response.json()
            )

        except httpx.HTTPError as error:

            raise ContableError(
                f"Error comunicando con "
                f"Sistema Contable: {error}"
            ) from error