# ABS Legal Documents – Review Checklist  
*(Entry‑point README for the ABS template suite: `dpa-template.md`, `subprocessors.md`, `privacy-policy.md`, `data‑retention-policy.md`)*  

---

## 1. Why These Are Templates  

The files in this folder are **generic starting points**, not ready‑to‑use contracts.  
- **No warranty** – ABS provides no guarantee that the language complies with any particular jurisdiction, industry regulation, or customer‑specific requirement.  
- **Customization required** – Each SaaS/AI offering has its own data flows, tooling, and corporate structure. The templates must be adapted to reflect the governing law of the entity, the actual sub‑processors you engage, and the contractual expectations of each customer.  
- **Legal risk** – Deploying an un‑customised template can expose the company to breach‑of‑contract, regulatory, or liability claims. Treat every document as a draft until a qualified counsel signs off.

---

## 2. Pre‑Publish Checklist  

> **All items must be completed and signed off before any version is shared with a customer or posted publicly.**  

| # | Action Item | What to Verify |
|---|-------------|----------------|
| 1 | **Counsel review** | Obtain written approval from in‑house or external counsel. Attach the review memo to the final file. |
| 2 | **Sub‑processor list current** | `subprocessors.md` must list every third‑party service you actually use, with up‑to‑date contact details and data‑processing agreements. |
| 3 | **Data categories match tooling** | Ensure the DPA's "Categories of Personal Data" align with the data captured by your product (e.g., email, IP address, biometric data). |
| 4 | **Retention periods accurate** | `data‑retention-policy.md` must reflect the real deletion schedule for each data category (e.g., "Log files – 90 days"). |
| 5 | **Governing‑law clause correct** | The clause must name the jurisdiction where the company is incorporated (or the jurisdiction agreed with the customer). |
| 6 | **Signature block proper entity** | The legal name, registration number, and address in the signature block must match the entity that will be bound by the agreement. |
| 7 | **Version & effective date stamped** | Add a version number (e.g., v1.3) and an "Effective Date" field; update the document header accordingly. |
| 8 | **Breach‑notification SLA realistic** | Verify that the SLA (e.g., "notify within 72 hours") can be met by your incident‑response team and that escalation procedures are documented. |
| 9 | **DSAR endpoint functional** | Test the Data Subject Access Request (DSAR) portal or email address; confirm that requests are routed, logged, and responded to within the contractual timeframe. |
|10| **Audit clause practical** | Ensure the audit rights (frequency, scope, on‑site vs. remote) are feasible for your organization size and resources. |
|11| **Indemnification cap negotiated** | Confirm that any indemnity limits (e.g., "capped at the fees paid in the preceding 12 months") have been agreed with the customer and are reflected in the template. |
|12| **Signature authority verified** | Document that the individual signing has proper corporate authority (e.g., board resolution, officer sign‑off). |

*All checklist items should be ticked off in a separate "Legal Review Tracker" spreadsheet, with reviewer name and date.*

---

## 3. Versioning  

- **Change‑log** – Append a markdown table at the end of each document: `Date | Version | Author | Summary of Changes`.  
- **Approval workflow** – Draft → Legal Review → Business Owner sign‑off → Final sign‑off by authorized signatory.  
- **Customer communication** – When a new version is issued, notify affected customers at least 30 days before the effective date, providing a summary of material changes and a link to the updated document.

---

## 4. Out‑of‑Scope  

The ABS templates **do not** address:  

- U.S. state‑level privacy statutes (e.g., California CCPA/CPRA, Virginia CDPA).  
- Federal U.S. privacy law (CCPA, HIPAA, etc.).  
- China's Personal Information Protection Law (PIPL) or other non‑EU/UK regimes.  

If you serve customers subject to any of these regimes, draft supplemental clauses or separate agreements.

---

## 5. Where to File the Executed Copy  

1. **Document Management System (DMS)** – Store the fully executed PDF in the "Legal → Contracts → Data Protection" folder.  
2. **Metadata** – Tag with: `Company`, `Customer`, `Effective Date`, `Version`, `Document Type`.  
3. **Retention** – Keep the executed copy for the longer of the contract term plus the statutory limitation period (typically 6 years) or the data‑retention period for the underlying personal data.  

---  

*Follow this checklist for every iteration of the ABS templates to ensure legal compliance, operational alignment, and audit readiness.*
