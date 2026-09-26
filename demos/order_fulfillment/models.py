"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Defines validated inputs, outputs, and shared state for the order workflow.
"""

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Quantity = Annotated[int, Field(strict=True, gt=0)]
Status = Literal[
    "confirmed", "invalid_request", "no_match", "out_of_stock", "insufficient_stock"
]


class OrderRequest(BaseModel):
    """Natural-language HTTP input for one order attempt."""

    model_config = ConfigDict(extra="forbid")
    request: Annotated[Name, Field(max_length=2000)]


class OrderItem(BaseModel):
    """Product and quantity extracted from the user's request."""

    product: Name
    quantity: Quantity


class ExtractedOrder(BaseModel):
    """Extraction result; unclear requests must return an empty item list."""

    items: list[OrderItem]


class Product(BaseModel):
    """One catalog entry, including explicit matching aliases."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    product_id: Name
    name: Name
    aliases: list[Name] = Field(default_factory=list)
    available: Annotated[int, Field(strict=True, ge=0)]


class OrderResponse(BaseModel):
    """Business outcome, including registration details when successful."""

    status: Status
    request: str
    message: str
    product: str | None = None
    quantity: int | None = None
    order_id: str | None = None
    available: int | None = None


class OrderState(TypedDict, total=False):
    """Per-request graph state; nodes return only changed fields."""

    request: str
    item: OrderItem
    product: Product
    status: Status
    available: int
    order_id: str
    response: OrderResponse
