> ⚠️ **DRAFT — LEGAL REVIEW REQUIRED**
> This document is a template provided as-is. Before signing with customers, qualified legal counsel review is mandatory. Automatia BCN takes no liability for unreviewed use. See `docs/legal/README.md` for review checklist.

**ABS – GDPR Privacy Policy**  

*(Version 1.0 – 27 April 2026)*  

---

### 1. Who we are  

ABS (Automatia Barcelona, S.L.) is a software‑as‑a‑service provider based in Barcelona, Spain. Our registered office is at **C/ Gran Via, 123, 08008 Barcelona, Spain**. You can reach us by e‑mail at **privacy@automatiabcn.com** or by post at the address above.  

We operate the ABS platform (the "Service") that lets developers and small teams create, test and run web‑applications. This privacy notice explains how we collect, use, store and protect any personal data that you (or your users) provide to us, in accordance with the EU General Data Protection Regulation (GDPR) (Regulation (EU) 2016/679).  

---

### 2. What personal data we collect  

| Category | Typical items | Why we need it |
|----------|---------------|----------------|
| **Account data** | Name, e‑mail address, phone number, password (hashed), profile picture, language preference | To create and manage your ABS account, authenticate you, and communicate about the Service. |
| **Usage data** | IP address, device type, browser version, timestamps, API‑call logs, feature‑usage statistics | To keep the Service running, detect abuse, improve performance and develop new features. |
| **Billing data** | Billing address, VAT number, credit‑card token (stored by our payment processor), invoice history | To issue invoices, process payments and comply with tax obligations. |
| **Audit data** | Change‑log entries, admin‑action records, security‑event alerts | To provide an audit trail for compliance, troubleshooting and security investigations. |
| **Support data** | Ticket content, screenshots, chat transcripts, optional recordings of voice calls | To answer your questions, resolve technical problems and improve support quality. |

All data are collected directly from you (e‑mail sign‑up, API calls, web‑forms) or automatically when you interact with the Service (e.g., logs). We never collect data about you from third‑party sources unless you explicitly provide it (e.g., linking a GitHub account).  

---

### 3. Lawful basis for processing  

Under **Article 6 GDPR** we rely on the following legal bases:  

| Basis | When it applies | What it means for you |
|-------|----------------|-----------------------|
| **Performance of a contract** (Art. 6 (1)(b)) | Whenever you create an ABS account, use the platform or request a paid plan. | Processing is necessary to deliver the Service you have ordered. |
| **Legitimate interests** (Art. 6 (1)(f)) | For fraud detection, security monitoring, system‑performance analytics, and improving the product. | We have performed a balancing test; our interests do not override your fundamental rights. |
| **Consent** (Art. 6 (1)(a)) | When you opt‑in to marketing communications, newsletters, or optional data‑sharing features (e.g., public leaderboards). | You may withdraw consent at any time without affecting the provision of the Service. |

When we rely on **consent**, we keep a record of when and how it was given, and we provide a clear, simple way to withdraw it (see Section 9).  

---

### 4. How long we keep your data  

We retain personal data only for as long as necessary for the purposes described in this notice, or as required by law. Specific retention periods are summarised below; the full schedule is available in our **[Data Retention Policy](#)** (link placeholder).  

| Data type | Retention period | Rationale |
|-----------|------------------|-----------| 
| **Account data** | Until you delete your account, or up to **365 days** after termination (to allow export and backup). | Enables re‑activation, legal compliance, and dispute resolution. |
| **Usage & audit logs** | **90 days** (rolling window). | Sufficient for security monitoring and troubleshooting. |
| **Billing & tax records** | **7 years** (as required by Spanish tax law). | Fiscal audit obligations. |
| **Support tickets** | **2 years** after ticket closure. | Quality control and possible future reference. |
| **Consent records** | Until you withdraw consent or the related processing ends. | Demonstrates lawful basis. |

When the retention period expires, data are either **pseudonymised** (e.g., logs stripped of identifiers) or **securely deleted**.  

---

### 5. Sub‑processors  

We use a limited set of trusted third‑party service providers (hosting, payment, email, analytics). Their names, purposes and data‑protection clauses are listed in our **[Sub‑processors Register](subprocessors.md)** (link placeholder).  

All sub‑processors are bound by **Standard Contractual Clauses (SCCs)** or an **EU‑Adequacy Decision** where applicable, and they must meet the same GDPR‑level safeguards we apply.  

---

### 6. International transfers  

ABS is hosted primarily on **Hetzner Online GmbH** (Germany). Hetzner benefits from the **EU‑US Data Privacy Framework** (formerly "EU‑US Privacy Shield") and an **adequacy decision** for the United Kingdom, so transfers to Hetzner are considered **adequate** under GDPR.  

For services that run in the United States (e.g., our payment processor **Stripe**, our email service **SendGrid**), we rely on **Standard Contractual Clauses** approved by the European Commission. We keep a copy of each SCC on file and make it available to data subjects upon request.  

All transfers are **encrypted in transit (TLS 1.2+)** and, where possible, at rest.  

---

### 7. Your GDPR rights  

You have the following rights under Articles 15‑22 GDPR. We will respond to any request **without undue delay and within one calendar month** (extensions possible for complex cases).  

| Right | What it means | How to exercise it |
|-------|---------------|-------------------|
| **Right of access** (Art. 15) | Obtain a copy of all personal data we hold about you. | Use the **Data‑Export endpoint** (`GET /v1/me/data-export`). |
| **Right to rectification** (Art. 16) | Request correction of inaccurate or incomplete data. | Update your profile via **PATCH `/v1/me/account`** or contact us. |
| **Right to erasure ("right to be forgotten")** (Art. 17) | Ask us to delete your personal data, subject to legal limits. | Delete your account via **DELETE `/v1/me/account`**; we will retain only the data required by law (e.g., tax records). |
| **Right to restriction of processing** (Art. 18) | Temporarily limit how we use your data. | Email **privacy@automatiabcn.com** with the specific restriction you need. |
| **Right to data portability** (Art. 20) | Receive your data in a structured, commonly‑used format and move it to another controller. | Same as "right of access"; the export file is provided in **JSON** and **CSV** formats. |
| **Right to object** (Art. 21) | Object to processing based on legitimate interests or direct marketing. | Email **privacy@automatiabcn.com**; we will cease the relevant processing unless we demonstrate compelling legitimate grounds. |
| **Right not to be subject to automated decision‑making** (Art. 22) | Request human review of any automated profiling that produces legal or similarly significant effects. | Currently we do not use automated decision‑making that produces such effects; if this changes we will inform you. |

If you believe we have not complied with your rights, you may lodge a complaint with the **Spanish Data Protection Agency (AEPD)**.  

---

### 8. How to use your rights  

| Action | API endpoint | Description | Example |
|--------|--------------|-------------|---------|
| **Export all personal data** | `GET /v1/me/data-export` | Returns a downloadable archive (JSON + CSV) of everything we store about you. | `curl -H "Authorization: Bearer <token>" https://api.abs.com/v1/me/data-export -o my‑abs‑data.zip` |
| **Update account details** | `PATCH /v1/me/account` | Send a JSON payload with the fields you want to change (e.g., `"email": "new@example.com"`). | `curl -X PATCH -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"email":"new@example.com"}' https://api.abs.com/v1/me/account` |
| **Delete your account** | `DELETE /v1/me/account` | Permanently removes your account and all non‑retained data. You will receive a confirmation e‑mail. | `curl -X DELETE -H "Authorization: Bearer <token>" https://api.abs.com/v1/me/account` |
| **Contact us directly** | N/A | Send a request to **privacy@automatiabcn.com** with a clear description of the right you wish to exercise. | `Subject: GDPR – Right of Access` |

All API calls require a valid **Bearer token** belonging to the requesting user. We verify the token before processing any data‑subject request.  

---

### 9. Cookies & similar technologies  

ABS uses only **strictly necessary** cookies to keep you logged in and to protect the Service.  

| Cookie name | Purpose | Lifetime | Security |
|-------------|---------|----------|----------|
| `abs_session` | Session identifier (HTTP‑Only, Secure) | 7 days of inactivity | Encrypted, SameSite = Lax |
| `abs_csrf` | CSRF token for form submissions | 7 days | HTTP‑Only, Secure |
| `abs_pref` | UI language & theme preference (non‑identifying) | 30 days | Not HttpOnly (client‑readable) |

We **do not** set tracking, advertising or analytics cookies that identify you across sites. If you give explicit consent (e.g., for a marketing newsletter), we will place a separate **consent cookie** that records the scope and date of consent; you can withdraw it at any time via the **account settings** page or by clearing your browser cookies.  

---

### 10. Children's privacy  

The Service is intended for **individuals aged 16 years or older** (the age of digital consent in most EU Member States).  

* We **do not knowingly collect** personal data from children under 13 years of age.  
* If we become aware that a child under 13 has provided personal data, we will delete it promptly.  
* Parents or guardians may contact us at **privacy@automatiabcn.com** to request removal of a child's data.  

---

### 11. Changes to this privacy notice  

We may update this privacy policy to reflect changes in the law, our practices, or new features.  

* **How you'll be notified:** We will send an e‑mail to the address on file for all active accounts **30 days before** the change takes effect. The e‑mail will contain a link to the revised notice.  
* **Versioning:** Each version is dated at the top of the document. The "Version 1.0 – 27 April 2026" you are reading now will be superseded by a new version number when we publish an update.  

If you continue to use the Service after the effective date, you are deemed to have accepted the revised terms.  

---

### 12. Contact us  

If you have any questions about this privacy notice, want to exercise a data‑subject right, or need clarification on any of the points above, please contact our Data Protection Officer (DPO) at:  

**E‑mail:** privacy@automatiabcn.com  
**Postal address:** DPO, Automatia Barcelona, S.L., C/ Gran Via 123, 08008 Barcelona, Spain  

We aim to acknowledge all inquiries within **five (5) business days**.  

---

> **This is a template — review with qualified legal counsel before adoption.**
