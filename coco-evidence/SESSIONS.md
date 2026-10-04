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
