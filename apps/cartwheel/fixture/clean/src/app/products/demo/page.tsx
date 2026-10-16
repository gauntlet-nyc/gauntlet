import Link from "next/link";

export default function DemoProduct() {
  return (
    <main style={{ padding: 16 }}>
      <h1>Demo Wheel</h1>
      <p>A synthetic wheel. $49.00</p>
      <Link href="/checkout" data-testid="product-checkout-link">
        Go to checkout
      </Link>
    </main>
  );
}
