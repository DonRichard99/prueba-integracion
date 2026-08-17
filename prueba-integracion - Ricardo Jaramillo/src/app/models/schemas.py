from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ItemVenta(BaseModel):
    sku: str = Field(..., min_length=1)
    descripcion: str = Field(..., min_length=1)
    cantidad: int = Field(..., gt=0)
    precio_unitario: float = Field(..., ge=0)


class Venta(BaseModel):
    id_venta: str = Field(..., min_length=1)
    id_cliente: str = Field(..., min_length=1)
    items: list[ItemVenta] = Field(..., min_length=1)
    total: float = Field(..., ge=0)
    canal: Literal["presencial", "ecommerce"]
    timestamp: datetime


class FacturaResponse(BaseModel):
    id_factura: str
    id_venta: str
    estado: Literal["Factura Emitida", "Factura Fallida"]
    timestamp_emision: datetime | None = None


class LealtadResponse(BaseModel):
    id_venta: str
    id_cliente: str
    estado: Literal["Puntos Acreditados", "Pendiente", "Rechazado"]
    puntos: int