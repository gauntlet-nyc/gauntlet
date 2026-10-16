// In-memory fake ledger. Refunds only append a record here; no payment provider exists.
export interface LedgerEntry {
  orderId: string;
  amountCents: number;
  requestedBy: string;
}

export class Ledger {
  private readonly entries: LedgerEntry[] = [];

  hasRefund(orderId: string): boolean {
    return this.entries.some((e) => e.orderId === orderId);
  }

  record(entry: LedgerEntry): void {
    this.entries.push(entry);
  }

  list(): readonly LedgerEntry[] {
    return this.entries;
  }
}
