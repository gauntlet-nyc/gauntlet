// Synthetic demo data only. No real customers, payments or contact details.
export interface Order {
  id: string;
  ownerId: string;
  totalCents: number;
}

export const ORDERS: Record<string, Order> = {
  "ord-2001": { id: "ord-2001", ownerId: "synthetic-owner-01", totalCents: 4900 },
  "ord-2002": { id: "ord-2002", ownerId: "synthetic-owner-02", totalCents: 7500 },
};
