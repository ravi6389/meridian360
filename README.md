# Meridian 360

**Customer 360 + Next Best Action engine for a P&C insurer, built entirely with Snowflake CoCo.**

Meridian 360 unifies structured policy, claim, and billing data with unstructured call transcripts, produces a single customer view with a transparent churn model, and recommends governed next best actions — complete with suppression guardrails, evidence trails, and one-click execution.

Every line of SQL, Python, and Streamlit in this repo was planned, authored, and executed by CoCo across a single build session. The session log in `coco-evidence/SESSIONS.md` documents every interaction.

## Architecture

```
RAW             7 tables, CSV seed data (synthetic, deterministic)
    |
CURATED         7 dynamic tables — cleansed, conformed, derived flags
    |
ENRICHED        630 transcripts processed by Cortex AI (claude-sonnet-4-5)
    |               sentiment, intent, churn signal, competitor, callback detection
SERVING         CUSTOMER_360 (41 columns, 9-signal churn model)
    |           NBA_RECOMMENDATION (7 action types, 12 suppression rules)
    |           CUSTOMER_TIMELINE, ACTION_LOG, V_SUPPRESSION_AUDIT
INTELLIGENCE    Cortex Search service, Semantic View (natural language analytics)
    |
APP             Streamlit dashboard (worklist, 360 view, governance tab)
                Nightly task (enrichment + guardrails at 2am IST)
```

All dynamic tables use `TARGET_LAG = '20 minutes'` and auto-refresh. The pipeline is fully declarative — no orchestration needed for the core flow.

## What It Demonstrates

| Capability | How It's Used |
|-----------|---------------|
| **Dynamic Tables** | 11 DTs form a self-refreshing pipeline from RAW to NBA_RECOMMENDATION |
| **Cortex AI (COMPLETE)** | 630 call transcripts enriched via claude-sonnet-4-5 — sentiment, intent, churn signals, competitor mentions, callback promises |
| **Cortex Search** | Natural language search over customer interactions |
| **Semantic View** | Business-friendly analytics layer for Cortex Analyst |
| **Streamlit** | 3-tab app: retention worklist, customer 360, governance dashboard |
| **Snowflake Tasks** | Nightly 2am IST pipeline: enrich new transcripts, refresh DTs, run 5 guardrail assertions |
| **MCP Integration** | Slack webhook via MCP server — PII-safe retention alerts posted from the NBA engine |
| **Stored Procedures** | Orchestration (SP_NIGHTLY_PIPELINE), enrichment (SP_REFRESH_ENRICHMENT), guardrails (SP_GUARDRAIL_CHECKS), action execution (SP_EXECUTE_ACTION) |

## Hero Customer: CUST-00001 (Arjun Mehta)

The demo storyline centers on a hand-authored hero customer with every signal deliberately wired:

- **12-year tenure**, single auto policy, no home coverage (bundle gap)
- **27.5% premium increase** on pending renewal (rate shock)
- **Open liability claim** for 74 days, not at fault (stalled claim)
- **3 phone calls** with declining sentiment: 0.38 → 0.18 → 0.04
- **Competitor quote** from Kavach General, 13,000 cheaper
- **4 web sessions** including cancellation page and rate comparison
- **Churn risk score: 0.53** (8 of 9 signals firing)

**Recommended actions:** Supervisor Rate Review, Proactive Win-Back, Loyalty Credit, Stalled Claim Escalation.
**Suppressed:** Home Bundle Cross-Sell (blocked by S01: open-claim freeze).

## Churn Model

Transparent weighted-additive model — every term is an inspectable column in CUSTOMER_360:

| Signal | Weight | Source |
|--------|--------|--------|
| Negative sentiment (recent 30d) | 0.20 | Call sentiment scores |
| Declining sentiment trajectory | 0.15 | Recent vs prior 30d window |
| Churn language (AI-detected) | 0.20 | Cortex AI transcript extraction |
| Competitor mention (AI-detected) | 0.15 | Cortex AI transcript extraction |
| Cancellation page views | 0.15 | Web session risk-page flag |
| Rate shock (>15% increase) | 0.25 | Policy renewal + competitor quote |
| Disputed/unresolved claims | 0.20 | Claim ageing + status |
| Payment distress | 0.15 | Billing past-due/collections |
| Mono-line household (no bundle) | 0.10 | Household LOB count |

Weights sum to 1.55 (intentionally >1.0 for full-range spread). Linear tenure dampener floored at 0.40.

## Suppression Rules (Guardrails)

12 rules enforce conduct, regulatory, and reputational risk:

| Rule | What It Blocks |
|------|---------------|
| S01 Open-claim freeze | Cross-sell to customers with open/reopened claims |
| S02 Litigation hold | All outbound for at-fault open claims with high reserves |
| S03 Denial cooling-off | Cross-sell within 90 days of claim denial |
| S04 Collections status | Cross-sell and loyalty offers to customers in collections |
| S05 Cancellation in progress | Cross-sell during active cancellation request |
| S07 Minor party | Marketing to customers under 18 |
| S08 Duplicate cooldown | Same action within 30 days |
| S09 Negative sentiment | Cross-sell during unresolved negative interaction |
| S10 Premium-shock grace | Cross-sell during rate shock period |
| S11 Over-contact | Non-urgent actions when 3+ contacts in 14 days |
| S12 Do-not-contact | All outbound for opted-out customers |

The nightly task runs 5 guardrail assertions and **fails loud** (exception, task FAILED state) if any violation is found.

## Nightly Automation

`APP.NIGHTLY_PIPELINE_REFRESH` — Snowflake Task, CRON `0 2 * * * Asia/Kolkata`:

1. **SP_REFRESH_ENRICHMENT** — finds new phone transcripts not yet in INTERACTION_AI, processes via claude-sonnet-4-5
2. **ALTER DYNAMIC TABLE ... REFRESH** — forces CUSTOMER_360 and NBA_RECOMMENDATION to pick up enrichment
3. **SP_GUARDRAIL_CHECKS** — 5 assertions (cross-sell to open claims, litigation hold, missing evidence, missing reason text, collections cross-sell)
4. If any assertion fails: raises exception -20001, task enters FAILED, auto-suspends after 3 consecutive failures

## Repo Structure

```
sql/
  01_setup.sql              Warehouse, database, schemas, role, stage
  02_raw_ddl.sql            RAW tables + SP_LOAD_SEED_DATA
  03_curated.sql            7 curated dynamic tables
  05_serving.sql            CUSTOMER_360, timeline, bundle gap, AI signals
  07_nba_engine.sql         Action catalog, suppression, NBA, action log

python/
  gen_synth.py              Synthetic data generator (500 customers, deterministic)
  validate.py               PK/FK validator + hero spot checks

streamlit/
  app.py                    3-tab Streamlit app (worklist, 360, governance)
  environment.yml           Streamlit-in-Snowflake dependencies

intelligence/
  meridian_analytics.sv.yaml  Semantic view for Cortex Analyst

mcp/
  slack-webhook/            MCP server for Slack notifications (reads URL from env)

coco-evidence/
  SESSIONS.md               Dated log of every CoCo interaction
  automations/              Nightly pipeline DDL

skills/
  synth-data-generator/     Reusable CoCo skill for synthetic data generation

docs/
  ontology.md               Entity definitions, keys, relationships
  architecture.md           Six-layer design, suppression rule catalogue
```

## Setup (From Scratch)

Requires a Snowflake account with Cortex AI access.

```bash
# 1. Generate synthetic data
cd python
python gen_synth.py          # outputs data/*.csv

# 2. Validate referential integrity
python validate.py           # 29 checks, all must pass

# 3. Run SQL in order (in Snowflake)
sql/01_setup.sql             # creates database, schemas, role, warehouse
sql/02_raw_ddl.sql           # creates RAW tables

# 4. Upload and load seed data
PUT file://data/*.csv @RAW.SEED_STAGE AUTO_COMPRESS=TRUE OVERWRITE=TRUE;
CALL RAW.SP_LOAD_SEED_DATA();

# 5. Build pipeline layers
sql/03_curated.sql           # curated dynamic tables
sql/05_serving.sql           # CUSTOMER_360, timeline, bundle gap
sql/07_nba_engine.sql        # action catalog, suppression, NBA engine

# 6. Enrich transcripts (one-time, uses Cortex AI credits)
# Run the enrichment process for INTERACTION_AI

# 7. Deploy Streamlit app
# CREATE STREAMLIT from streamlit/app.py
```

## CoCo Evidence

This project was built for evaluation on demonstrable CoCo usage. Every session is logged in `coco-evidence/SESSIONS.md` covering:

- Design planning (ontology, architecture, suppression rules)
- Infrastructure setup and RAW DDL
- Synthetic data generation with causal transcript linking
- Full pipeline build (curated, enrichment, serving, NBA engine)
- Streamlit app with 3-tab layout
- Slack MCP integration with PII boundary enforcement
- Nightly automation with fail-loud guardrails
- Reusable skill packaging

## Data

All data is synthetic, generated by `python/gen_synth.py` with `seed=42`. Names, addresses, phone numbers, and policy numbers are fabricated. No production data exists in this project.

CSVs are excluded from git (see `.gitignore`). Regenerate with `python gen_synth.py`.
