from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str


class ProductIn(BaseModel):
    sku: str
    name: str
    description: str = ""
    category_id: int
    brand: str = "Lumen"
    price: Decimal
    cost: Decimal
    weight_grams: int = 500


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    name: str
    description: str
    brand: str
    price: Decimal
    category_id: int
    is_active: bool
