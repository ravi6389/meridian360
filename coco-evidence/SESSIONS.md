# Meridian 360 — CoCo Session Log

## 2026-10-04 — Design docs: ontology and architecture

**What CoCo was asked to do:**
Read the AGENTS.md governance file and produce two design documents before any
SQL implementation:

1. `docs/ontology.md` — entity definitions, keys, relationships, churn signals
2. `docs/architecture.md` — six-layer design with Snowflake object types per
   layer, plus a comprehensive suppression-rule catalogue for conduct,
   regulatory, and reputational risk

**What CoCo produced:**
- Entity ontology covering Party, Household, Policy, Claim, Billing,
  Interaction, and Quote, with full attribute tables, join paths, and a
  churn-signal weighting summary.
- Architecture document mapping RAW (tables) → CURATED (views) → ENRICHED
  (dynamic tables) → SERVING (dynamic tables + append-only table) →
  INTELLIGENCE (Cortex Search + Semantic Model) → APP (Streamlit + procedures),
  with rationale for each object-type choice.
- 12 suppression rules (S01–S12) covering open-claim freeze, litigation hold,
  denial cooling-off, collections, cancellation in progress, regulatory
  blackout, minors, duplicate cooldown, negative sentiment, premium shock,
  excessive contact, and do-not-contact, with SQL implementation pattern.

## 2026-10-04 — Infrastructure setup and RAW DDL

**What CoCo was asked to do:**
Create the MERIDIAN database, all schemas, warehouse, stage, file format, and
RAW landing tables. Execute against Snowflake and confirm objects exist.

**What CoCo produced:**
- `sql/01_setup.sql` — warehouse, database, 6 schemas, MERIDIAN_BUILDER role
  with grants, internal stage, CSV file format.
- `sql/02_raw_ddl.sql` — 7 RAW tables with PK constraints, plus
  `SP_LOAD_SEED_DATA()` procedure.
- All objects executed and confirmed live in Snowflake.

## 2026-10-04 — Synthetic data generation and loading

**What CoCo was asked to do:**
Write a synthetic data generator with causally linked transcripts, a
hand-authored hero customer (CUST-00001), a referential integrity validator,
then generate, validate, and load into RAW.

**What CoCo produced:**
- `python/gen_synth.py` — deterministic generator (seed=42) producing 500
  parties, 310 households, 711 policies, 201 claims, 1,982 billing events,
  1,225 interactions (630 phone transcripts with causal tone linking), 193
  quotes. Hero CUST-00001 with 12-year tenure, 27.5% premium increase, disputed
  claim open 74 days, 3 declining-sentiment calls naming Kavach General, 4 web
  page views, competitor quote 13,000 cheaper, and household bundle gap.
- `python/validate.py` — validates PK uniqueness (7 tables) and FK integrity
  (10 relationships) plus 12 hero-specific spot checks. All 29 checks passed.
- CSVs uploaded to `@RAW.SEED_STAGE` and loaded via `SP_LOAD_SEED_DATA()`.
  All row counts confirmed in Snowflake.

## 2026-10-04 — Curated + Serving layers, Enrichment, NBA engine, Streamlit app

**What CoCo was asked to do:**
Build the full pipeline from curated dynamic tables through enrichment, serving,
NBA engine, and Streamlit app deployment across multiple iterative steps.

**What CoCo produced:**

**Curated layer** (`sql/03_curated.sql`):
7 dynamic tables (TARGET_LAG 20min): DT_CUSTOMER (party+household rollup,
tenure), DT_POLICY (days-to-renewal, rate-shock flag), DT_CLAIM (ageing,
unresolved flag), DT_BILLING (payment-distress flag), DT_WEB_SESSION (risk-page
flag), DT_QUOTE, DT_INTERACTION (transcript passthrough).

**Serving layer** (`sql/05_serving.sql`):
- CUSTOMER_360 dynamic table: 41-column one-row-per-customer view with 9-signal
  weighted-additive churn model (weights sum > 1.0 for full-range spread, linear
  tenure dampener floor 0.40). Each signal is an inspectable column. Reason
  codes as ARRAY. AI signals wired from ENRICHED.V_AI_SIGNALS.
- CUSTOMER_TIMELINE: unified event stream across all domains.
- DT_HOUSEHOLD_BUNDLE_GAP: cross-sell opportunity detection.
- V_RETENTION_WORKLIST: 45-day renewal window, dual ranking (expected loss and
  churn risk), cross-sell flag.

**AI Enrichment:**
- ENRICHED.INTERACTION_AI: 630 transcripts processed via claude-sonnet-4-5
  with single-call JSON extraction (sentiment, intent, churn signal, complaint,
  competitor, life event, callback, resolution, summary, key quote).
- 100% parse success rate after markdown-fence stripping.
- V_AI_SIGNALS: per-party aggregation feeding CUSTOMER_360.

**NBA Engine** (`sql/07_nba_engine.sql`):
- ACTION_CATALOG: 7 action types across RETENTION, CROSS_SELL, SERVICE, RISK.
- DT_SUPPRESSION: 12 rules from architecture.md as dynamic table.
- NBA_RECOMMENDATION: candidate generation per action type, scoring as
  propensity × EV × urgency, suppression via LEFT JOIN.
- ACTION_LOG: append-only audit trail.
- V_SUPPRESSION_AUDIT: guardrail dashboard.

**Streamlit App** (`streamlit/app.py`):
- Tab 1 (Worklist): retention worklist with sort toggle, churn progress bars.
- Tab 2 (Customer 360): profile header with warning badges, Plotly sentiment
  trajectory chart, timeline, NBA panel with recommended/suppressed cards and
  action execution.
- Tab 3 (Governance): suppression audit, enrichment QA metrics, rule book.
- Deployed as `MERIDIAN.APP.MERIDIAN_360` via CREATE STREAMLIT.

**CUST-00001 verification:**
- Churn risk 0.53 (rank #1 by score), 8 of 9 signals firing.
- 4 recommended actions (Supervisor Rate Review flagged for approval,
  Proactive Win-Back, Loyalty Credit, Stalled Claim Escalation).
- Home Bundle Cross-Sell present but SUPPRESSED by S01 + S05 + S10.
- Sentiment trajectory declining across 3 calls (0.38 → 0.18 → 0.04).

## 2026-10-04 — Slack MCP action + Nightly pipeline automation

**What CoCo was asked to do:**
1. Read the Supervisor Rate Review recommendation for CUST-00001 and post a
   PII-safe retention alert to Slack via the MCP tool.
2. Set up a nightly automation at 2am IST: refresh enrichment for new
   transcripts, regenerate recommendations, run guardrail validation, fail
   loudly on any assertion failure.

**What CoCo produced:**

**Slack MCP action:**
- Read NBA_RECOMMENDATION for CUST-00001 Supervisor Rate Review (NBA Score
  3211.16, $45.9K premium at risk, 8 reason codes).
- Posted PII-safe alert via `mcp_slack_send_slack_message` — party ID, action
  name, summary, reason codes, evidence ref only. No customer name or raw
  transcript text (AGENTS.md Rule 7 compliant).
- Logged action in SERVING.ACTION_LOG (Rule 4 compliant).

**Nightly pipeline automation:**
- CoCo automations not available on trial account — fell back to Snowflake Task.
- `ENRICHED.SP_REFRESH_ENRICHMENT()` — incremental Cortex enrichment of new
  phone transcripts via claude-sonnet-4-5 with JSON parsing and markdown-fence
  stripping.
- `SERVING.SP_GUARDRAIL_CHECKS()` — 5 assertions: G1 no cross-sells to
  open-claim customers, G2 no actions under litigation hold, G3 every
  recommendation carries evidence (Rule 6), G4 REASON_TEXT populated, G5 no
  cross-sells to COLLECTIONS customers.
- `APP.SP_NIGHTLY_PIPELINE()` — orchestrator: enrich → refresh DTs → assert →
  fail loud. Uses SYSTEM$SET_RETURN_VALUE for task history visibility.
- `APP.NIGHTLY_PIPELINE_REFRESH` — Snowflake Task, CRON `0 2 * * *
  Asia/Kolkata`, SUSPEND_TASK_AFTER_NUM_FAILURES = 3.
- Manual test run passed: 0 new transcripts, all 5 guardrails green.
- Finding: 9 HOME_BUNDLE_CROSS_SELL rows have empty REASON_CODES (low-churn
  customers qualifying via bundle gap). EVIDENCE_REF populated, so Rule 6
  conjunction is satisfied. Noted for future NBA engine fix.
- All DDL saved to `coco-evidence/automations/nightly_pipeline.sql`.
- GRANT EXECUTE TASK ON ACCOUNT issued to MERIDIAN_BUILDER via ACCOUNTADMIN.

## 2026-10-05 — Trial cost containment + Streamlit usability

**What CoCo was asked to do:**
Stop background credit burn ($400 → $147 in a day) and improve the app for
first-time viewers.

**What CoCo produced:**
- Suspended all 12 dynamic tables and set TARGET_LAG = DOWNSTREAM (6 were FULL
  refresh every 20 minutes because of CURRENT_DATE / CURRENT_TIMESTAMP).
- Cortex Search INTERACTION_SEARCH target lag raised 1 hour → 24 hours.
- Nightly task NIGHTLY_PIPELINE_REFRESH suspended.
- Resource monitor MERIDIAN_RM (40 credits, notify 75%, suspend 90%, hard stop
  100%) attached to MERIDIAN_WH.
- `APP.SP_WAKE_FOR_DEMO()` — one CALL resumes and refreshes all 12 DTs in
  dependency order before recording.
- Streamlit: new "How it works" first tab with per-tab walkthroughs and worked
  examples; labelled Worklist column headers with hover definitions; "Ask me
  anything" box answering what/why/how questions at customer or portfolio
  scope, grounded in Cortex Search results plus portfolio statistics, with the
  prompt passed as a bind parameter.

## 2026-10-05 — MCP connection testing

**What CoCo was asked to do:** Prove the Slack MCP connection was tested.

**What CoCo produced:**
- `mcp/slack-webhook/test.mjs` (`npm test`): drives the real server over stdio
  with the MCP SDK client against a local mock webhook. Covers the startup
  guard, handshake, tools/list, the call path, unknown tool, a Slack 400 and a
  network failure. 16/16 checks passed; log in `coco-evidence/mcp-tests/`.
- `coco-evidence/mcp-tests/README.md`: test results plus the live 2026-10-04
  Slack post and its ACTION_LOG row.
