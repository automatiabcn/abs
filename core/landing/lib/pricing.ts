/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// What we charge, in one place.
//
// Before 2026-08-03 the answer depended on which file you opened. Stripe — the
// thing that actually takes the money — charges $29 a month for one person and
// $19 per seat for a team. Meanwhile three READMEs, seven documents, the site
// FAQ, the pricing page's own search description and the **terms of service**
// described a retired model: a $299 one-off "Self-Host Lifetime" licence with
// an optional $49/year maintenance pack. None of that has been purchasable for
// months, and the terms are a contract.
//
// The prices themselves were never wrong. What was wrong is that they were
// written down in twenty places, so correcting one taught the others nothing —
// the same shape as the dead download host in August. Hence a module: the page
// reads from here, and a test compares these numbers against the Stripe setup
// script, so the sentence a customer reads and the amount their card is
// charged cannot drift apart silently.

/** Dollars per month for one person. Stripe: unit_amount 2900. */
export const SOLO_PRICE = 29;

/** Dollars per seat per month. Stripe: unit_amount 1900, quantity = seats. */
export const TEAM_SEAT_PRICE = 19;

/** Below this, Solo is the cheaper answer and the team plan makes no sense. */
export const MIN_TEAM_SEATS = 3;

/** Every install starts here, and it does not ask for a card. */
export const TRIAL_DAYS = 7;

/** The same length, spelled the way a sentence wants it.
 *
 * "7 days free, no card" is worse prose than "Seven days free, no card", and
 * the marketing copy should not be paying for the single-source rule. Both are
 * exported, and a test asserts they agree — so the drift this file exists to
 * prevent cannot sneak back in through the word. */
export const TRIAL_LABEL = "Seven days";

/** "$29" — so no surface has to remember the symbol or the number. */
export function priceLabel(dollars: number): string {
  return `$${dollars}`;
}
