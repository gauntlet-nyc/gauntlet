export default function Checkout() {
  return (
    <main style={{ padding: 16, paddingBottom: 96 }}>
      <h1>Checkout</h1>
      <p>1 x Demo Wheel, $49.00</p>
      <footer
        style={{
          position: "fixed", left: 0, right: 0, bottom: 0, padding: 16,
          display: "flex", justifyContent: "flex-end", background: "#fff", borderTop: "1px solid #ddd",
        }}
      >
        <button type="button" data-testid="checkout-primary-action" style={{ padding: "12px 20px" }}>
          Place order
        </button>
      </footer>
    </main>
  );
}
