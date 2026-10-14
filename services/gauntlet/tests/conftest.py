"""Builds a small throwaway Git repository with a UI change and an AI-tool change."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

CHECKOUT_BUTTON = """export function CheckoutButton() {
  return (
    <button data-testid="checkout-primary-action" className="w-full py-3">
      Checkout
    </button>
  );
}
"""

CHECKOUT_PAGE = """import { CheckoutButton } from "../../components/CheckoutButton";

export default function CheckoutPage() {
  return <main><CheckoutButton /></main>;
}
"""

REFUND_TOOL_BASE = """export async function requestRefund(ctx, orderId) {
  const order = await ctx.orders.get(orderId);
  if (order.ownerId !== ctx.actorId) {
    throw new Error("forbidden");
  }
  return ctx.ledger.refund(order.id, order.total);
}
"""

REFUND_TOOL_HEAD = """export async function requestRefund(ctx, orderId) {
  const order = await ctx.orders.get(orderId);
  return ctx.ledger.refund(order.id, order.total);
}
"""

FLOATING_HELP = """export function FloatingHelp() {
  return (
    <button className="fixed bottom-4 right-4 z-50 rounded-full">
      Help
    </button>
  );
}
"""


@dataclass(frozen=True)
class DemoRepo:
    path: Path
    base: str
    ui_head: str
    tool_head: str


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return result.stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture
def demo_repo(tmp_path: Path) -> DemoRepo:
    repo = tmp_path / "cartwheel"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "web/src/components/CheckoutButton.tsx", CHECKOUT_BUTTON)
    _write(repo, "web/src/app/checkout/page.tsx", CHECKOUT_PAGE)
    _write(repo, "api/src/tools/request_refund.ts", REFUND_TOOL_BASE)
    _write(repo, "README.md", "demo\n")
    _write(repo, ".env", "API_KEY=placeholder\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _write(repo, "web/src/components/FloatingHelp.tsx", FLOATING_HELP)
    _write(repo, ".env", "API_KEY=changed-placeholder\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add floating help")
    ui_head = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", base)
    _write(repo, "api/src/tools/request_refund.ts", REFUND_TOOL_HEAD)
    _git(repo, "commit", "-q", "-am", "simplify refund tool")
    tool_head = _git(repo, "rev-parse", "HEAD")
    return DemoRepo(path=repo, base=base, ui_head=ui_head, tool_head=tool_head)
