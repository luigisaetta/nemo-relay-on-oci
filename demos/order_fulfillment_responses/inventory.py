"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Loads the independent Responses API demo catalog and simulates orders.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import TypeAdapter

from demos.order_fulfillment_responses.models import OrderItem, Product


def normalize(value: str) -> str:
    """Normalize a product name for exact matching.

    Args:
        value: Product name or alias.

    Returns:
        Case-folded text with normalized whitespace.
    """
    return " ".join(value.casefold().split())


@dataclass
class Inventory:
    """In-memory stock and orders for this process only.

    Attributes:
        products: Validated catalog entries keyed by identifier.
        orders: Successful simulated registrations.
    """

    products: dict[str, Product]
    orders: list[dict] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def load(cls, path: Path) -> "Inventory":
        """Read a nonempty unique-ID catalog.

        Args:
            path: JSON catalog file.

        Returns:
            Initialized inventory.

        Raises:
            ValueError: The catalog is empty or has duplicate identifiers.
            OSError: The catalog cannot be read.
        """
        products = TypeAdapter(list[Product]).validate_python(
            json.loads(path.read_text(encoding="utf-8"))
        )
        by_id = {product.product_id: product for product in products}
        if not products or len(by_id) != len(products):
            raise ValueError("Catalog must be nonempty and have unique product IDs")
        return cls(by_id)

    def match(self, name: str) -> list[Product]:
        """Find exact normalized name or alias matches.

        Args:
            name: Extracted product name.

        Returns:
            Matching catalog products.
        """
        return [
            product
            for product in self.products.values()
            if normalize(name)
            in {normalize(candidate) for candidate in [product.name, *product.aliases]}
        ]

    def available(self, product_id: str) -> int:
        """Read stock while holding the registration lock.

        Args:
            product_id: Catalog identifier.

        Returns:
            Current availability.
        """
        with self._lock:
            return self.products[product_id].available

    def register(self, product_id: str, quantity: int) -> dict:
        """Atomically reserve stock and record an order.

        Args:
            product_id: Selected catalog identifier.
            quantity: Positive quantity to reserve.

        Returns:
            Simulated registration result.

        Raises:
            ValueError: The product identifier or quantity is invalid.
        """
        OrderItem(product=product_id, quantity=quantity)
        with self._lock:
            if product_id not in self.products:
                raise ValueError("Unknown product ID")
            product = self.products[product_id]
            if product.available < quantity:
                return {
                    "status": (
                        "out_of_stock"
                        if product.available == 0
                        else "insufficient_stock"
                    ),
                    "available": product.available,
                }
            order_id = str(uuid4())
            remaining = product.available - quantity
            self.products[product_id] = product.model_copy(
                update={"available": remaining}
            )
            self.orders.append(
                {"order_id": order_id, "product_id": product_id, "quantity": quantity}
            )
            return {"status": "confirmed", "order_id": order_id, "available": remaining}

    def registration_tool(self) -> StructuredTool:
        """Expose simulated registration as a traceable LangChain tool.

        Returns:
            Tool bound to this inventory.
        """
        return StructuredTool.from_function(
            self.register,
            name="register_order",
            description="Simulate registering an order and reserve available stock.",
        )
