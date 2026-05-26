from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PlaceOrderItemIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = 1


class PlaceOrderIn(BaseModel):
    customer_id: int
    items: list[PlaceOrderItemIn]
    channel: str = "direct"
    device_type: str = "desktop"
    promo_code: str | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_number: str
    status: str
    grand_total: Decimal
    placed_at: datetime
    items: list[OrderItemOut]
