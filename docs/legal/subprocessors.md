> ⚠️ **DRAFT — LEGAL REVIEW REQUIRED**
> This document is a template provided as-is. Before signing with customers, qualified legal counsel review is mandatory. Automatia BCN takes no liability for unreviewed use. See `docs/legal/README.md` for review checklist.

# Sub-processors Register

**Automatia ABS, S.L.**  
*Version 1.0 – Effective 27 April 2026*

---

## Overview

Automatia ABS, S.L. (the "Processor") uses the following sub-processors to deliver the ABS platform and related services to customers (the "Controller"). This register lists each sub-processor's name, purpose, the categories of personal data processed, the location where data is stored or processed, and the legal basis for the transfer.

All sub-processors are bound by written contracts that impose the same level of data-protection safeguards as ABS itself applies under GDPR Article 28.

---

## Sub-processors Table

| # | Sub-processor | Purpose / Function | Categories of Data | Location | Legal Basis |
|---|---------------|--------------------|-------------------|----------|-------------|
| 1 | **Stripe, Inc.** | Payment processing, billing, invoice storage, refund flow | Email, billing address, payment method tokens (PCI tokenised, not full card numbers) | San Francisco, USA | Standard Contractual Clauses (SCCs); Stripe maintains a valid DPA |
| 2 | **Anthropic, Inc.** (optional, customer-enabled) | Large Language Model (LLM) inference for optional provider feature | API request metadata, token counts, usage logs; no prompt content retained by Anthropic | San Francisco, USA | Standard Contractual Clauses (SCCs); Anthropic DPA in place |
| 3 | **Groq, Inc.** (optional, customer-enabled) | Large Language Model (LLM) inference for optional provider feature | Prompts, completions, token usage; processed transiently, not stored | San Francisco, USA | Standard Contractual Clauses (SCCs) |
| 4 | **Google Cloud (Alphabet, Inc.)** (optional, customer-enabled) | Gemini API inference for optional provider feature | API calls, usage statistics, request metadata | Mountain View / Multi-region, USA | Standard Contractual Clauses (SCCs); Google Cloud DPA available |
| 5 | **Cloudflare, Inc.** (optional, customer-enabled) | Edge compute, request routing, optional security features | API calls, metadata, request headers, IP addresses | San Francisco, USA (with EU edge replication) | Standard Contractual Clauses (SCCs); Cloudflare DPA in place |
| 6 | **Cohere** (optional, customer-enabled) | Large Language Model (LLM) inference for optional provider feature | Prompts, completions, token counts | Toronto / USA data centres | Standard Contractual Clauses (SCCs); adequacy decision (Canada-EU mutual recognition) |
| 7 | **OpenRouter** (optional, customer-enabled) | LLM provider aggregation and routing | API calls, usage logs, model routing metadata | USA | Standard Contractual Clauses (SCCs) |
| 8 | **Hetzner Online GmbH** | Hosting of ABS licensing service, manifest server, backup infrastructure | License metadata (customer ID, JWT tokens), API audit logs, manifest data, IP logs, uptime monitoring | Nuremberg, Germany (EU) | Data Processing Agreement (DPA) with Hetzner; EU-EU transfer (no SCCs required) |

---

## How to be Notified of Changes

1. **Notification Period:** When ABS BCN engages a new sub-processor or makes a material change to an existing sub-processor's scope or role, we will notify affected customers **at least 30 calendar days in advance** via email to the primary contact address on file.

2. **Notification Content:** Each notification will include:
   - Name and location of the new or modified sub-processor
   - Description of the processing activities to be performed
   - Categories of personal data that will be processed
   - Legal basis for the transfer (e.g., SCCs, adequacy decision)
   - A link to this register (which will be updated)

3. **Feedback Period:** Customers will have **10 calendar days** from the date of notification to review the change and submit any concerns to privacy@automatiabcn.com.

---

## Right to Object

1. **Objection Mechanism:** If a customer objects to the engagement of a new sub-processor or a material change to an existing sub-processor, the customer must notify ABS BCN in writing (email to privacy@automatiabcn.com) **within 14 calendar days** of the notification date.

2. **Objection Content:** The objection should specify:
   - The name of the sub-processor
   - The reason(s) for the objection
   - Any alternative solutions the customer proposes

3. **ABS Response:** ABS BCN will acknowledge the objection within 5 business days and will attempt to discuss an alternative solution in good faith with the customer.

4. **Resolution:**
   - If ABS BCN and the customer reach agreement on an alternative, processing will proceed under the agreed terms.
   - If no agreement is reached and the customer continues to object, the customer may:
     - Request immediate termination of the Service Agreement without penalty, provided that the termination is requested before the new sub-processor's engagement effective date.
     - Allow the change to proceed and accept the new sub-processor by continuing to use the Service after the effective date.

5. **No Penalty:** A customer's exercise of the right to object to a sub-processor change will not result in additional charges, service downgrade, or termination of the contract, provided that the customer acts within the stated timelines.

---

## Data Security & Sub-processor Liability

- All sub-processors are contractually bound to maintain a level of security consistent with **GDPR Article 32** (encryption, access controls, incident logging, regular security testing).
- ABS BCN remains **fully liable** to the customer for any breach of data-protection obligations by its sub-processors.
- Customers may request evidence of compliance (e.g., SOC 2 Type II certificates) from ABS BCN, which will be provided within 10 business days.

---

## Changes to This Register

This sub-processors register is reviewed and updated at least quarterly. Any addition, deletion, or material change is documented with a version number and effective date. The latest version is always available at [link to this document].

**Current version:** 1.0 – Effective 27 April 2026

---

> **This is a template — review with qualified legal counsel before adoption.**
