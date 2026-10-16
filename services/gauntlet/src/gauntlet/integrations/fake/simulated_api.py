"""OFFLINE simulation of Cartwheel's synthetic orders API (transcribed from the fixture's
route handlers) as an httpx transport. ``accept_invalid=True`` models a broken validator."""

import json
import uuid

import httpx


def cartwheel_orders_transport(*, accept_invalid: bool = False) -> httpx.MockTransport:
    orders: dict[str, dict[str, object]] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/api/orders":
            try:
                body = json.loads(request.content or b"null")
            except ValueError:
                return httpx.Response(400, json={"error": "invalid request"})
            valid = (
                isinstance(body, dict)
                and body.get("item_id") == "demo-wheel"
                and body.get("quantity") == 1
            )
            if not valid and not accept_invalid:
                return httpx.Response(400, json={"error": "invalid synthetic item"})
            order: dict[str, object] = {
                "order_id": str(uuid.uuid4()),
                "item_id": "demo-wheel",
                "quantity": body.get("quantity") if isinstance(body, dict) else None,
                "amount_minor": 4900,
                "currency": "USD",
                "status": "placed",
                "synthetic": True,
            }
            orders[str(order["order_id"])] = order
            return httpx.Response(201, json=order)
        if request.method == "GET" and path.startswith("/api/orders/"):
            found = orders.get(path.rsplit("/", 1)[-1])
            if found is None:
                return httpx.Response(404, json={"error": "order not found"})
            return httpx.Response(200, json=found)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handle)
