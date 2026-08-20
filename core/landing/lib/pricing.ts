/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What we charge, in one place.
//
// One plan, $5 a month (founder's decision, 2026-08-03). There is no Solo/Team
// split any more: a tier list is a question asked of someone who came here to
// buy, and the answer was the same product either way.
//
// This module exists because of what came before it. Stripe charged $29 and
// $19/seat, while three READMEs, seven documents, the site FAQ, the pricing
// page's own search description and the terms of service still described a
// $299 one-off "Self-Host Lifetime" licence with a $49/year maintenance pack —
// retired months earlier and not purchasable. The numbers were never wrong;
// they were written down in twenty places, so correcting one taught the others
// nothing. A test compares the number below against the Stripe setup script,
// so the sentence a customer reads and the amount their card is charged cannot
// drift apart again.

/** Dollars per month. Stripe: unit_amount 500. */
export const PRICE = 5;

/** Every install starts here, and it does not ask for a card. */
export const TRIAL_DAYS = 7;

/** The same length, spelled the way a sentence wants it.
 *
 * "7 days free, no card" is worse prose than "Seven days free, no card", and
 * the copy should not be paying for the single-source rule. Both are exported,
 * and a test asserts they agree. */
export const TRIAL_LABEL = "Seven days";

/** "$5" — so no surface has to remember the symbol or the number. */
export function priceLabel(dollars: number): string {
  return `$${dollars}`;
}
