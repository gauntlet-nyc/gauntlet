import { orderStore, type Order } from "../../../lib/orders";

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid request" }, { status: 400 });
  }
  if (
    typeof body !== "object" || body === null ||
    !("item_id" in body) || body.item_id !== "demo-wheel" ||
    !("quantity" in body) || body.quantity !== 1
  ) {
    return Response.json({ error: "invalid synthetic item" }, { status: 400 });
  }
  const order: Order = {
    order_id: crypto.randomUUID(), item_id: "demo-wheel", quantity: 1,
    amount_minor: 4900, currency: "USD", status: "placed", synthetic: true,
  };
  orderStore().set(order.order_id, order);
  return Response.json(order, { status: 201 });
}
