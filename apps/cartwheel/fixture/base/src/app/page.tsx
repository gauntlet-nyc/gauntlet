import Link from "next/link";

export default function Home() {
  return (
    <main style={{ padding: 16 }}>
      <h1>Cartwheel</h1>
      <Link href="/products/demo">Demo product</Link>
    </main>
  );
}
