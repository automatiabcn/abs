# ABS Private Beta Agreement — Template

> **NOT LEGAL ADVICE.** This is a starting point. Run any final version past
> Spanish + EU counsel before sending to a customer. Automatia BCN
> (Barcelona, Spain) is the contracting entity.

## Parties

This agreement (the "Agreement") is entered into on `{{ effective_date }}` between:

- **Provider:** Automatia BCN, Barcelona, Spain (the "Provider").
- **Customer:** `{{ customer_legal_name }}`, `{{ customer_address }}` (the "Customer").

## 1. Scope

The Provider grants the Customer access to the ABS Server product (the
"Service") under the terms of this Agreement for a 90-day private beta period
("Beta Period") commencing on the Effective Date.

## 2. Fees

No fees are payable during the Beta Period. The Customer agrees that converting
to a paid plan after the Beta Period is at the Customer's sole discretion.

## 3. Customer Obligations

The Customer agrees to:

- Provide written feedback weekly via the agreed channel.
- Make a single technical contact available for a 30-minute call once per month.
- Use the Service only on a non-production / pilot scope agreed at kickoff.
- Report any security findings to `security@abs-server.example.com` within 5 business days.

## 4. Provider Obligations

The Provider agrees to:

- Maintain the Service with best-effort uptime — no SLA during the Beta Period.
- Triage P0 incidents within 1 business hour and deliver a fix or workaround
  within 48 business hours when the issue is reproducible.
- Process Customer data only for the purposes described in
  `docs/legal/dpa-template.md`, attached as Schedule A.

## 5. Confidentiality

Each party will treat the other's non-public information as confidential and
will not disclose it for the duration of the Agreement plus 3 years thereafter.
Neither party will publicly attribute statements to the other without written
consent.

## 6. Data Protection

The parties enter into the Data Processing Agreement at Schedule A. The
Customer is the controller; the Provider is the processor.

## 7. Anonymised Case Study

The Customer grants the Provider the right to publish an anonymised case study
describing the engagement after the Beta Period. The Customer's identity will
not appear without separate written consent.

## 8. Termination

Either party may terminate this Agreement on 7 days' written notice. On
termination, the Provider will provide a data export within 30 days as
described in `docs/data-retention-policy.md`.

## 9. Limitation of Liability

To the maximum extent permitted by law, neither party's aggregate liability
under this Agreement exceeds €1,000.

## 10. Governing Law

This Agreement is governed by the laws of Spain. Disputes will be resolved by
the courts of Barcelona.

## Signatures

| For Provider | For Customer |
|---|---|
| `{{ provider_signatory }}` | `{{ customer_signatory }}` |
| `{{ provider_title }}` | `{{ customer_title }}` |
| Date: ________ | Date: ________ |
