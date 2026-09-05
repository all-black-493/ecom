from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AddToCartIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(1, ge=1, le=99)


class UpdateCartItemIn(BaseModel):
    quantity: int = Field(..., ge=0, le=99)  # 0 = remove


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: Decimal
    product_name: str | None = None
    product_sku: str | None = None
    line_total: Decimal | None = None


class CartTotalsOut(BaseModel):
    item_count: int
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    grand_total: Decimal


class CartOut(BaseModel):
    id: int
    status: str
    items: list[CartItemOut]
    totals: CartTotalsOut
