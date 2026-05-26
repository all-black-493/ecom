from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InventoryLevel(Base):
    """Current on-hand stock per variant per warehouse."""

    __tablename__ = "inventory_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(20), default="MAIN")
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=10)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_inventory_variant_warehouse", "variant_id", "warehouse_code"),)


class StockMovement(Base):
    """Append-only log of stock changes — gold for inventory analytics."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), index=True)
    warehouse_code: Mapped[str] = mapped_column(String(20), default="MAIN")
    delta: Mapped[int] = mapped_column(Integer)  # +receipt / -sale / -shrinkage
    reason: Mapped[str] = mapped_column(String(40))  # purchase, sale, return, adjustment
    ref_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
