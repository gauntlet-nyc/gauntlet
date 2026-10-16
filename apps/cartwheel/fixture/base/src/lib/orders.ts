export type Order = {
  order_id: string;
  item_id: "demo-wheel";
  quantity: 1;
  amount_minor: 4900;
  currency: "USD";
  status: "placed";
  synthetic: true;
};

const processState = globalThis as typeof globalThis & { cartwheelSyntheticOrders?: Map<string, Order> };

export function orderStore(): Map<string, Order> {
  return (processState.cartwheelSyntheticOrders ??= new Map<string, Order>());
}
