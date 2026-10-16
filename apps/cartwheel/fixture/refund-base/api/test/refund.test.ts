import assert from "node:assert/strict";
import { test } from "node:test";

import { Ledger } from "../src/ledger.ts";
import { requestRefund } from "../src/tools/request_refund.ts";

test("an owner can refund their own order once", () => {
  const ledger = new Ledger();
  const result = requestRefund({ actorId: "synthetic-owner-01", ledger }, { orderId: "ord-2001" });
  assert.equal(result.refundedCents, 4900);
  assert.equal(ledger.list().length, 1);
  assert.throws(() => requestRefund({ actorId: "synthetic-owner-01", ledger }, { orderId: "ord-2001" }));
});
