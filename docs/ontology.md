# Meridian 360 — Entity Ontology

## Entities

### Party (unification point)

The anchor entity. Every person or organisation that interacts with the insurer
resolves to exactly one Party record, regardless of how many policies, claims or
channels they appear in.

| Attribute | Type | Notes |
|---|---|---|
| `PARTY_ID` | `VARCHAR` (PK, `CUST-NNNNN`) | Surrogate key, prefixed |
| `FIRST_NAME` | `VARCHAR` | |
| `LAST_NAME` | `VARCHAR` | |
| `DATE_OF_BIRTH` | `DATE` | |
| `EMAIL` | `VARCHAR` | |
| `PHONE` | `VARCHAR` | |
| `MAILING_ADDRESS` | `VARCHAR` | Single-line formatted |
| `STATE` | `VARCHAR(2)` | US state code |
| `POSTAL_CODE` | `VARCHAR(10)` | |
| `CREATED_AT` | `TIMESTAMP_NTZ` | First appearance in any source |
| `HOUSEHOLD_ID` | `VARCHAR` (FK) | Links to Household |

**Churn signals sourced from Party:** age band (younger customers churn faster
in personal lines), tenure (derived from `CREATED_AT`), state (regulatory
environment affects retention).

---

### Household

Groups co-resident Parties who share insurable interests. Bundle-gap analysis
operates at Household level: a household with Auto but no Home is the canonical
cross-sell opportunity.

| Attribute | Type | Notes |
|---|---|---|
| `HOUSEHOLD_ID` | `VARCHAR` (PK, `HH-NNNNN`) | Surrogate key |
| `ADDRESS` | `VARCHAR` | Primary address of the household |
| `STATE` | `VARCHAR(2)` | |
| `POSTAL_CODE` | `VARCHAR(10)` | |
| `MEMBER_COUNT` | `NUMBER` | Count of linked Parties |

**Churn signals sourced from Household:** bundle depth (mono-line households
churn at ~2x the rate of multi-line), household size (single-member households
are less sticky).

---

### Policy

An active or lapsed insurance contract. A Party may hold multiple Policies; a
Policy belongs to exactly one Party (the named insured). Lines of business:
Auto, Home, Umbrella, Renters.

| Attribute | Type | Notes |
|---|---|---|
| `POLICY_ID` | `VARCHAR` (PK, `POL-NNNNN`) | Surrogate key |
| `PARTY_ID` | `VARCHAR` (FK) | Named insured |
| `LINE_OF_BUSINESS` | `VARCHAR` | `AUTO`, `HOME`, `UMBRELLA`, `RENTERS` |
| `STATUS` | `VARCHAR` | `ACTIVE`, `CANCELLED`, `EXPIRED`, `PENDING_RENEWAL` |
| `EFFECTIVE_DATE` | `DATE` | |
| `EXPIRATION_DATE` | `DATE` | |
| `PREMIUM_AMOUNT` | `NUMBER(12,2)` | Annual written premium |
| `DEDUCTIBLE` | `NUMBER(12,2)` | |
| `COVERAGE_LIMIT` | `NUMBER(12,2)` | |
| `BIND_DATE` | `DATE` | Date the policy was bound |
| `CANCELLATION_DATE` | `DATE` | NULL if still active |
| `RENEWAL_COUNT` | `NUMBER` | Times renewed, 0 = new business |

**Churn signals sourced from Policy:** status = `PENDING_RENEWAL` with no
renewal activity, premium increase > 15% at renewal, low renewal count,
coverage-limit reduction (customer may be shopping).

---

### Claim

A first-notice-of-loss (FNOL) through to settlement. A Claim references one
Policy; a Policy may have many Claims.

| Attribute | Type | Notes |
|---|---|---|
| `CLAIM_ID` | `VARCHAR` (PK, `CLM-NNNNN`) | Surrogate key |
| `POLICY_ID` | `VARCHAR` (FK) | |
| `PARTY_ID` | `VARCHAR` (FK) | Claimant (usually = policy holder) |
| `LOSS_DATE` | `DATE` | |
| `REPORT_DATE` | `DATE` | |
| `CLAIM_STATUS` | `VARCHAR` | `OPEN`, `CLOSED`, `REOPENED`, `DENIED` |
| `CLAIM_TYPE` | `VARCHAR` | `COLLISION`, `PROPERTY_DAMAGE`, `LIABILITY`, `WEATHER`, `THEFT` |
| `RESERVE_AMOUNT` | `NUMBER(12,2)` | |
| `PAID_AMOUNT` | `NUMBER(12,2)` | |
| `FAULT_INDICATOR` | `VARCHAR` | `AT_FAULT`, `NOT_AT_FAULT`, `PARTIAL` |

**Churn signals sourced from Claim:** denied claims (strongest single predictor
of voluntary churn), claim frequency >= 2 in 12 months, long cycle time
(REPORT_DATE to closure), adverse fault finding.

---

### Billing

Payment events and receivable state. One row per billing event per Policy.

| Attribute | Type | Notes |
|---|---|---|
| `BILLING_ID` | `VARCHAR` (PK, `BIL-NNNNN`) | Surrogate key |
| `POLICY_ID` | `VARCHAR` (FK) | |
| `PARTY_ID` | `VARCHAR` (FK) | |
| `DUE_DATE` | `DATE` | |
| `AMOUNT_DUE` | `NUMBER(12,2)` | |
| `AMOUNT_PAID` | `NUMBER(12,2)` | |
| `PAYMENT_DATE` | `DATE` | NULL if unpaid |
| `PAYMENT_METHOD` | `VARCHAR` | `ACH`, `CARD`, `CHECK`, `ONLINE` |
| `BILLING_STATUS` | `VARCHAR` | `PAID`, `PAST_DUE`, `GRACE`, `COLLECTIONS` |

**Churn signals sourced from Billing:** missed payments (1+ past-due), payment
method downgrade (ACH -> Check), switch from auto-pay to manual, balance in
collections.

---

### Interaction

Every touchpoint: inbound call, outbound call, email, chat, web self-service,
agent note. Unstructured content (call transcripts) lands here and feeds Cortex
AI summarisation and sentiment classification.

| Attribute | Type | Notes |
|---|---|---|
| `INTERACTION_ID` | `VARCHAR` (PK, `INT-NNNNNN`) | Surrogate key |
| `PARTY_ID` | `VARCHAR` (FK) | |
| `CHANNEL` | `VARCHAR` | `PHONE`, `EMAIL`, `CHAT`, `WEB`, `AGENT_NOTE` |
| `DIRECTION` | `VARCHAR` | `INBOUND`, `OUTBOUND` |
| `INTERACTION_DATE` | `TIMESTAMP_NTZ` | |
| `DURATION_SECONDS` | `NUMBER` | For calls |
| `TOPIC` | `VARCHAR` | e.g. `BILLING_INQUIRY`, `CLAIM_STATUS`, `CANCELLATION_REQUEST` |
| `TRANSCRIPT_TEXT` | `VARCHAR(16777216)` | Raw transcript (PII boundary applies) |
| `SUMMARY` | `VARCHAR` | Cortex-generated summary |
| `SENTIMENT` | `VARCHAR` | `POSITIVE`, `NEUTRAL`, `NEGATIVE`, `MIXED` |
| `SENTIMENT_SCORE` | `NUMBER(5,4)` | 0 = most negative, 1 = most positive |
| `RESOLUTION` | `VARCHAR` | `RESOLVED`, `ESCALATED`, `FOLLOW_UP`, `UNRESOLVED` |
| `RELATED_POLICY_ID` | `VARCHAR` (FK, nullable) | If interaction is policy-specific |
| `RELATED_CLAIM_ID` | `VARCHAR` (FK, nullable) | If interaction is claim-specific |

**Churn signals sourced from Interaction:** negative sentiment on 2+ recent
calls, cancellation-request topic, escalated resolution, high call frequency
(3+ in 30 days).

---

### Quote (optional / web-session derived)

Captures competitive-shopping behaviour from web sessions or agent systems.

| Attribute | Type | Notes |
|---|---|---|
| `QUOTE_ID` | `VARCHAR` (PK, `QUO-NNNNN`) | Surrogate key |
| `PARTY_ID` | `VARCHAR` (FK) | NULL for anonymous sessions |
| `LINE_OF_BUSINESS` | `VARCHAR` | |
| `QUOTED_PREMIUM` | `NUMBER(12,2)` | |
| `QUOTE_DATE` | `DATE` | |
| `QUOTE_STATUS` | `VARCHAR` | `QUOTED`, `BOUND`, `EXPIRED`, `DECLINED` |
| `SOURCE` | `VARCHAR` | `WEB`, `AGENT`, `PARTNER` |

**Churn signals sourced from Quote:** existing customer requesting a new quote
on a line they already hold (price-shopping), quote-to-bind conversion failure.

---

## Relationship Map

```
Household 1───* Party
Party      1───* Policy
Party      1───* Interaction
Party      1───* Billing  (also reachable via Policy)
Party      1───* Quote
Policy     1───* Claim
Policy     1───* Billing
Interaction *───0..1 Policy  (RELATED_POLICY_ID)
Interaction *───0..1 Claim   (RELATED_CLAIM_ID)
```

### Join paths

| From | To | Via |
|---|---|---|
| Customer 360 | All policies | `PARTY.PARTY_ID = POLICY.PARTY_ID` |
| Customer 360 | Claims | `PARTY → POLICY → CLAIM` or `CLAIM.PARTY_ID` |
| Customer 360 | Billing health | `PARTY → BILLING` or `PARTY → POLICY → BILLING` |
| Customer 360 | Interactions | `PARTY.PARTY_ID = INTERACTION.PARTY_ID` |
| Household bundle gaps | Policies held | `HOUSEHOLD → PARTY → POLICY`, pivot on `LINE_OF_BUSINESS` |
| Interaction context | Related claim/policy | Nullable FKs on Interaction |

---

## Churn Signal Summary

Signals are combined in the Enriched layer into a composite churn-propensity
score (0..1). Each signal contributes a weighted component.

| Signal | Source Entity | Weight Band | Rationale |
|---|---|---|---|
| Denied claim | Claim | High | Strongest single predictor of voluntary departure |
| Cancellation-request call | Interaction | High | Explicit intent signal |
| Negative sentiment (2+ calls) | Interaction | High | Emotional disengagement |
| Missed payments | Billing | Medium-High | Financial friction / disengagement |
| Mono-line household | Household | Medium | No bundling lock-in |
| Premium increase > 15% | Policy | Medium | Price shock at renewal |
| Pending renewal, no activity | Policy | Medium | Silent non-renewal risk |
| High call frequency | Interaction | Medium | Effort / frustration signal |
| Low tenure (< 2 years) | Party | Medium-Low | Less relationship inertia |
| Payment method downgrade | Billing | Low-Medium | Behavioural disengagement |
| Price-shopping quote | Quote | Low-Medium | Competitive exploration |
| Coverage-limit reduction | Policy | Low | May be optimising, not leaving |
