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
