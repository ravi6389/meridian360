# Meridian 360 — Architecture & Suppression Design

## Layer Architecture

All objects live in the `MERIDIAN` database. Each schema represents a logical
layer with increasing business meaning and decreasing latency tolerance.

---

### 1. RAW

**Purpose:** Immutable landing zone for source-system extracts and synthetic
seed data. No transformations, no joins, no derived columns.

**Snowflake object type:** `TABLE` (persistent, created with `CREATE TABLE IF
NOT EXISTS`).

**Why tables:** Raw data is loaded once via `COPY INTO` from staged CSVs.
Tables preserve the exact source shape for auditability and replay. No
computation required — just storage.

**Contents:**

| Table | Source |
|---|---|
| `RAW.PARTY` | Synthetic customer master |
| `RAW.HOUSEHOLD` | Synthetic household groupings |
| `RAW.POLICY` | Synthetic policy admin system |
| `RAW.CLAIM` | Synthetic claims system |
| `RAW.BILLING` | Synthetic billing/AR system |
| `RAW.INTERACTION` | Synthetic CRM / telephony |
| `RAW.QUOTE` | Synthetic web / quoting engine |

---

### 2. CURATED

**Purpose:** Cleansed, typed, deduplicated, conformed. Business keys validated,
nulls handled, enums standardised. Still one table per source entity — no joins
across entities yet.

**Snowflake object type:** `VIEW` (created with `CREATE OR REPLACE VIEW`).

**Why views:** Curated logic is lightweight (casts, trims, coalesces, case
statements). Views avoid data duplication and stay in sync with RAW
automatically. No materialisation cost for an XSMALL warehouse with a small
synthetic dataset.

**Contents:**

| View | Logic |
|---|---|
| `CURATED.V_PARTY` | Trim names, standardise state codes, validate email format |
| `CURATED.V_HOUSEHOLD` | Derive member count if not present, validate keys |
| `CURATED.V_POLICY` | Cast dates, validate LOB enum, derive policy age |
| `CURATED.V_CLAIM` | Validate status transitions, calculate cycle time |
| `CURATED.V_BILLING` | Classify payment status, calculate days-past-due |
| `CURATED.V_INTERACTION` | Normalise channel names, validate sentiment range |
| `CURATED.V_QUOTE` | Validate premium ranges, standardise LOB codes |

---

### 3. ENRICHED

**Purpose:** Cross-entity joins, AI-derived columns, feature engineering. This
is where Cortex functions run (sentiment analysis, summarisation) and where
churn signals are computed.

**Snowflake object type:** `DYNAMIC TABLE` with `TARGET_LAG = '1 hour'` (dev)
/ `'20 minutes'` (demo).

**Why dynamic tables:** Enrichment joins multiple curated views and calls
Cortex AI functions — these are expensive to re-compute on every query. Dynamic
tables materialise the result and refresh incrementally, giving the serving
layer fast reads without manual orchestration. Snowflake manages the refresh
DAG automatically.

**Contents:**

| Dynamic Table | Joins / Logic |
|---|---|
| `ENRICHED.DT_CUSTOMER_PROFILE` | Party + Household + policy count + LOBs held + tenure |
| `ENRICHED.DT_POLICY_FEATURES` | Policy + premium-change %, renewal gap, coverage changes |
| `ENRICHED.DT_CLAIM_FEATURES` | Claim + cycle time, denied flag, fault, frequency per party |
| `ENRICHED.DT_BILLING_HEALTH` | Billing + missed-payment count, auto-pay flag, days-past-due |
| `ENRICHED.DT_INTERACTION_ENRICHED` | Interaction + Cortex sentiment + Cortex summary + topic |
| `ENRICHED.DT_CHURN_SIGNALS` | Union of all signal sources → per-party weighted churn score |
| `ENRICHED.DT_HOUSEHOLD_BUNDLE` | Household → Policies pivot → bundle-gap flags (has_auto, has_home, etc.) |

---

### 4. SERVING

**Purpose:** Business-ready aggregates and the NBA recommendation table. This
is the contract the Streamlit app and any external integration reads from.

**Snowflake object type:** Mix of `DYNAMIC TABLE` (for the 360 view and
recommendations) and `TABLE` (for the action log, which is append-only and must
never be replaced).

**Why:** The 360 view and recommendations must stay fresh as enriched data
updates — dynamic tables handle this. The action log records executed
actions and must survive re-deployments, so it is a persistent table with
`CREATE TABLE IF NOT EXISTS`.

**Contents:**

| Object | Type | Purpose |
|---|---|---|
| `SERVING.DT_CUSTOMER_360` | Dynamic Table | Single-row-per-customer master view joining all enriched tables |
| `SERVING.NBA_RECOMMENDATION` | Dynamic Table | One row per party per recommended action, ranked, with reason codes and evidence refs |
| `SERVING.V_SUPPRESSION` | View | Returns party + action combinations that must be suppressed (see Suppression Rules below) |
| `SERVING.ACTION_LOG` | Table (append-only) | Immutable audit trail of executed actions with recommendation ID, timestamp, channel, outcome |

---

### 5. INTELLIGENCE

**Purpose:** Cortex-powered analytical capabilities that sit on top of the
serving layer. Semantic model for Cortex Analyst, search service for
transcript retrieval.

**Snowflake object type:** `CORTEX SEARCH SERVICE` for unstructured retrieval,
Cortex Analyst `SEMANTIC MODEL` (YAML) for natural-language BI.

**Why:** Cortex Search gives servicing agents instant retrieval over
interaction summaries without writing SQL. Cortex Analyst lets managers ask
ad-hoc questions ("which households have the highest churn risk?") against a
governed semantic model rather than raw tables.

**Contents:**

| Object | Type | Purpose |
|---|---|---|
| `INTELLIGENCE.INTERACTION_SEARCH` | Cortex Search Service | Full-text + semantic search over interaction summaries |
| `intelligence/semantic_model.yaml` | Cortex Analyst Semantic Model | Metrics, dimensions, relationships over SERVING.DT_CUSTOMER_360 and NBA_RECOMMENDATION |

---

### 6. APP

**Purpose:** The Streamlit application, stored procedures for action execution,
and any UDFs needed by the app.

**Snowflake object type:** `STREAMLIT` app, `PROCEDURE`, `FUNCTION`.

**Why:** Streamlit-in-Snowflake keeps the app inside the governance boundary —
no data leaves Snowflake. Stored procedures enforce the action-logging rule
(hard rule 4 in AGENTS.md): every external write goes through a procedure that
inserts into `ACTION_LOG` before calling the external API.

**Contents:**

| Object | Type | Purpose |
|---|---|---|
| `APP.MERIDIAN_360` | Streamlit | Agent-facing dashboard: customer search, 360 view, NBA cards, one-click actions |
| `APP.SP_EXECUTE_ACTION` | Procedure | Validates recommendation exists, checks suppression, logs to ACTION_LOG, dispatches |
| `APP.SP_LOG_ACTION` | Procedure | Pure audit insert into ACTION_LOG |

---

## Layer Flow Diagram

```
  RAW (tables)
    │  COPY INTO from staged CSVs
    ▼
  CURATED (views)
    │  Cleanse, type, conform
    ▼
  ENRICHED (dynamic tables)
    │  Join, Cortex AI, feature engineering
    ▼
  SERVING (dynamic tables + append-only table)
    │  Customer 360, NBA, Suppression, Action Log
    ▼
  INTELLIGENCE (Cortex Search + Semantic Model)
    │  NL querying, transcript retrieval
    ▼
  APP (Streamlit + procedures)
       Agent UI, action execution
```

---

## Suppression Rules

Suppression prevents the system from recommending actions that would be wrong,
harmful, or illegal for a regulated insurer. Every suppression rule maps to a
concrete risk category and becomes a predicate in `SERVING.V_SUPPRESSION`.

The NBA engine must left-join `V_SUPPRESSION` and either exclude or flag
matched rows before any recommendation reaches the UI.

### Rule Catalogue

| # | Rule Name | Action Suppressed | Condition | Risk Category | Rationale |
|---|---|---|---|---|---|
| S01 | **Open-claim freeze** | Cross-sell, upsell, renewal offer | Party has any claim with `CLAIM_STATUS IN ('OPEN','REOPENED')` | Conduct / regulatory | Soliciting during an active claim creates a conflict of interest and may violate unfair-trade-practices statutes. The customer is in a vulnerable moment. |
| S02 | **Litigation hold** | All outbound actions | Party has a claim where `CLAIM_STATUS = 'OPEN'` AND `FAULT_INDICATOR = 'AT_FAULT'` AND `RESERVE_AMOUNT > PAID_AMOUNT * 2` (proxy for disputed/litigated) | Regulatory / legal | Any contact with a potentially litigating customer must go through legal counsel. Automated outreach could prejudice the insurer's position. |
| S03 | **Recent denial cooling-off** | Upsell, cross-sell | Party had a `DENIED` claim within the last 90 days | Conduct / reputational | Selling more coverage to someone whose claim was just denied is tone-deaf and may trigger regulatory complaints. |
| S04 | **Collections status** | Upsell, cross-sell, loyalty reward | Party has any billing record with `BILLING_STATUS = 'COLLECTIONS'` | Regulatory | Marketing to a customer in collections may violate state debt-collection regulations and is reputationally dangerous. |
| S05 | **Cancellation in progress** | Cross-sell, upsell | Party has a policy with `STATUS = 'CANCELLED'` and `CANCELLATION_DATE` within last 30 days, OR an interaction with `TOPIC = 'CANCELLATION_REQUEST'` in last 14 days | Conduct | The customer has expressed intent to leave. Pushing new products before resolving the cancellation driver is counterproductive and may feel coercive. |
| S06 | **Regulatory blackout (state-specific)** | Renewal offers, rate-change communications | Policy is in a state with an active regulatory moratorium (e.g., post-catastrophe rate-freeze states) | Regulatory | Several states impose moratoriums on cancellations and rate increases after declared disasters. The system must suppress actions that would violate these orders. Implemented via a reference table of active moratoriums. |
| S07 | **Minor party** | All marketing/sales actions | `DATE_OF_BIRTH` indicates party is under 18 | Regulatory / conduct | Minors cannot enter insurance contracts in most jurisdictions. Marketing to them is a compliance violation. |
| S08 | **Duplicate action cooldown** | Same action type | `ACTION_LOG` shows the same `(PARTY_ID, ACTION_TYPE)` was executed within the last 30 days | Conduct / reputational | Prevents spamming the same recommendation. One touch per action type per month. |
| S09 | **Negative-sentiment active conversation** | Upsell, cross-sell | Party has an interaction in the last 7 days with `SENTIMENT = 'NEGATIVE'` and `RESOLUTION IN ('ESCALATED','UNRESOLVED')` | Conduct / reputational | Selling to a customer who is actively upset and unresolved is likely to escalate the situation and generate complaints. Resolve first, sell later. |
| S10 | **Premium-shock grace period** | Upsell, premium-increase communication | Policy renewal within last 30 days had a premium increase > 15% | Conduct / reputational | The customer just absorbed a price shock. Pushing more spend immediately is poor customer experience and increases churn risk. Allow 30 days for the new rate to settle. |
| S11 | **Excessive contact frequency** | All non-urgent outbound | Party has 3+ outbound interactions in the last 14 days | Conduct | Over-contact erodes trust and may trigger TCPA or state telemarketing violations depending on channel. |
| S12 | **Do-not-contact flag** | All outbound | Party has an interaction with `TOPIC = 'DO_NOT_CONTACT'` or equivalent flag | Regulatory | Respecting opt-out preferences is legally required under CAN-SPAM, TCPA, and state privacy laws. |

### Implementing the Suppression View

`SERVING.V_SUPPRESSION` returns one row per `(PARTY_ID, ACTION_TYPE,
SUPPRESSION_RULE)` combination. Structure:

```
PARTY_ID        VARCHAR
ACTION_TYPE     VARCHAR     -- e.g. 'CROSS_SELL', 'UPSELL', 'RENEWAL_OFFER', '*' for all
RULE_ID         VARCHAR     -- e.g. 'S01'
RULE_NAME       VARCHAR
REASON          VARCHAR     -- Human-readable explanation
SUPPRESSED_AT   TIMESTAMP_NTZ
EXPIRES_AT      TIMESTAMP_NTZ  -- NULL = indefinite until condition clears
```

The view is a `UNION ALL` of one `SELECT` per rule, each encoding its condition
as a `WHERE` clause against the relevant enriched/serving tables. The NBA
engine applies it with:

```sql
SELECT r.*
FROM   SERVING.NBA_RECOMMENDATION r
LEFT JOIN SERVING.V_SUPPRESSION s
  ON r.PARTY_ID = s.PARTY_ID
  AND (s.ACTION_TYPE = r.ACTION_TYPE OR s.ACTION_TYPE = '*')
WHERE  s.PARTY_ID IS NULL   -- not suppressed
```

Suppressed recommendations can optionally be surfaced in the UI with a visual
indicator and the suppression reason, but they must never appear as actionable.
