import { orderStore } from "../../../../lib/orders";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await context.params;
  const order = orderStore().get(id);
  if (!order) return Response.json({ error: "order not found" }, { status: 404 });
  return Response.json(order, { headers: { "cache-control": "no-store" } });
}
