import { ORDERS } from "../data.ts";
import type { Ledger } from "../ledger.ts";

export interface ToolContext {
  actorId: string;
  ledger: Ledger;
}

export interface RefundResult {
  orderId: string;
  refundedCents: number;
}

export function requestRefund(ctx: ToolContext, input: { orderId: string }): RefundResult {
  const order = ORDERS[input.orderId];
  if (!order) {
    throw new Error("unknown order");
  }
  if (order.ownerId !== ctx.actorId) {
    throw new Error("forbidden: order belongs to another customer");
  }
  if (ctx.ledger.hasRefund(order.id)) {
    throw new Error("order already refunded");
  }
  ctx.ledger.record({ orderId: order.id, amountCents: order.totalCents, requestedBy: ctx.actorId });
  return { orderId: order.id, refundedCents: order.totalCents };
}
