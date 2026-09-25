"""JSON catalog loading and thread-safe simulated order registration."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import TypeAdapter

from demos.order_fulfillment.models import OrderItem, Product


def normalize(value: str) -> str:
    """Normalize a name for exact matching.

    Args:
        value: Product name or alias.

    Returns:
        Case-folded text with normalized whitespace.
    """
    return " ".join(value.casefold().split())


@dataclass
class Inventory:
    """In-memory stock and orders, shared by requests in one server process.

    Attributes:
        products: Validated catalog entries, keyed by ID.
        orders: Successful simulated registrations.
    """

    products: dict[str, Product]
    orders: list[dict] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def load(cls, path: Path) -> "Inventory":
        """Read and validate the catalog once at startup.

        Args:
            path: JSON catalog file.

        Returns:
            Inventory initialized from the catalog.

        Raises:
            ValueError: Entries are invalid, empty, or have duplicate IDs.
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
        """Find all exact name or alias matches.

        Args:
            name: Extracted product name.

        Returns:
            Matching entries; callers reject zero or multiple matches.
        """
        return [
            product
            for product in self.products.values()
            if normalize(name)
            in {normalize(n) for n in [product.name, *product.aliases]}
        ]

    def available(self, product_id: str) -> int:
        """Read current stock under the registration lock.

        Args:
            product_id: Catalog identifier.

        Returns:
            Current available quantity.
        """
        with self._lock:
            return self.products[product_id].available

    def register(self, product_id: str, quantity: int) -> dict:
        """Atomically check stock and record a simulated order.

        Args:
            product_id: Catalog identifier selected by the graph.
            quantity: Positive integer quantity to reserve.

        Returns:
            Registration outcome and current stock, with an ID on success.

        Raises:
            ValueError: Quantity is invalid or the product does not exist.
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
            # Recheck and decrement in the same critical section to avoid overselling.
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
        """Expose registration as a traceable LangChain tool.

        Returns:
            Tool bound to this inventory instance.
        """
        return StructuredTool.from_function(
            self.register,
            name="register_order",
            description="Simulate registering an order and atomically reserve available stock.",
        )
