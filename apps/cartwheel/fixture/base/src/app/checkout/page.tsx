"use client";

import { useState } from "react";

export default function Checkout() {
  const [orderId, setOrderId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(false);

  async function placeOrder() {
    if (submitting || orderId) return;
    setSubmitting(true);
    setError(false);
    try {
      const response = await fetch("/api/orders", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ item_id: "demo-wheel", quantity: 1 }),
      });
      if (!response.ok) throw new Error("synthetic order request failed");
      const receipt: { order_id: string } = await response.json();
      setOrderId(receipt.order_id);
    } catch {
      setError(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ padding: 16, paddingBottom: 96 }}>
      <h1>Checkout</h1>
      <p>1 x Demo Wheel, $49.00</p>
      {orderId && <p role="status" data-testid="order-receipt" data-order-id={orderId}>Order placed: {orderId}</p>}
      {error && <p role="alert">Could not place the synthetic order. Try again.</p>}
      <footer
        style={{
          position: "fixed", left: 0, right: 0, bottom: 0, padding: 16,
          display: "flex", justifyContent: "flex-end", background: "#fff", borderTop: "1px solid #ddd",
        }}
      >
        <button type="button" data-testid="checkout-primary-action" disabled={submitting || !!orderId}
          onClick={placeOrder} style={{ padding: "12px 20px" }}>
          {submitting ? "Placing order…" : "Place order"}
        </button>
      </footer>
    </main>
  );
}
