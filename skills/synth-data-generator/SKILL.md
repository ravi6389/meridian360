---
name: synth-data-generator
description: "Generate referentially consistent synthetic data for Customer 360 / NBA / churn demos. Use when building a demo dataset, seeding RAW tables, creating a hero customer storyline, or generating correlated transcripts for any insurance, lending, or telecom Next Best Action project. Triggers: synthetic data, demo data, seed data, generate test data, hero customer, churn demo, NBA demo, fake transcripts, Customer 360 seed."
---

# Synthetic Data Generator for Customer 360 + NBA Demos

Generate a complete, referentially consistent synthetic dataset with hand-authored hero storylines, causally correlated transcripts, and guardrail-tripping test customers. Ships with P&C insurance defaults and retargeting notes for lending and telecom.

## When to Use

- Seeding a new Customer 360 / Next Best Action project
- Rebuilding demo data after schema changes
- Adding hero customers that exercise specific pipeline paths
- Creating guardrail-tripping test cases for suppression rules
- Porting the generator to a different industry vertical

## Design Rules (Learned the Hard Way)

These are non-negotiable. Every one caused a silent data bug in production before it became a rule.

### 1. Hand-author the hero storyline

Random data is boring data. A demo lives or dies on whether the hero customer tells a compelling, inspectable story. Never rely on random generation to produce an interesting customer.

**Pattern:** Generate all random data first, then *purge* the hero's random rows and inject hand-authored replacements. The hero's policies, claims, billing, interactions, and quotes are all written as explicit code, not random draws.

**Why:** A randomly generated CUST-00001 will have contradictory signals (e.g. a HOME policy that negates the bundle gap storyline, or sentiment scores that don't decline). Hand-authoring guarantees every signal fires as designed.

### 2. Purge before inject

Before injecting hero data, delete ALL random data for hero IDs across every table. Otherwise the hero inherits random policies, claims, and billing rows that contradict the intended story.

```python
# Purge ALL random data for hero party IDs
hero_ids = {"CUST-00001", "CUST-00002"}
hero_pols = {p["POLICY_ID"] for p in policies if p["PARTY_ID"] in hero_ids}
policies[:]     = [p for p in policies     if p["PARTY_ID"] not in hero_ids]
claims[:]       = [c for c in claims       if c["PARTY_ID"] not in hero_ids]
billing[:]      = [b for b in billing      if b["PARTY_ID"] not in hero_ids]
interactions[:] = [i for i in interactions  if i["PARTY_ID"] not in hero_ids]
quotes[:]       = [q for q in quotes       if q.get("PARTY_ID") not in hero_ids]
```

**Why:** Without the purge, CUST-00001 had a randomly generated HOME policy. This made the bundle-gap cross-sell disappear, and the suppression rule S01 stopped firing for the hero. The demo was broken but the pipeline ran clean — the worst kind of bug.

### 3. Anchor all dates to CURRENT_DATE at generation time

Every date offset must be computed from `date.today()` / `datetime.now()`, not from hardcoded calendar dates.

```python
TODAY = date.today()
NOW = datetime.now()
expiration = TODAY + timedelta(days=23)        # renews in 23 days
call_date  = NOW - timedelta(days=9)           # called 9 days ago
```

**Why:** Recency signals (30-day sentiment window, 14-day cancellation window, 45-day renewal horizon) all use `CURRENT_DATE()` in the SQL pipeline. If data dates are hardcoded to e.g. "2025-06-15", then 6 months later every interaction falls outside every window. The churn model returns zero for all signals, the pipeline appears healthy (no errors), and every recommendation silently goes wrong. This bug is invisible unless you spot-check the hero.

### 4. Correlate unstructured tone with structured events

Transcript tone must match the customer's structured situation. A customer with a 27% premium increase and a 74-day unresolved claim should sound angry, not neutral.

**Pattern:** After generating structured data, compute each customer's "situation" (premium shock, stalled claim, billing distress), then select transcript templates and sentiment scores based on that situation.

```
Structured event          Transcript tone    Sentiment score
No issues                 positive/neutral   0.45-0.95
Premium increase 5-15%    concerned          0.35-0.45
Premium increase >15%     frustrated→angry   0.08-0.32
Claim open >30 days       frustrated→angry   0.08-0.32
Billing in collections    concerned          0.35-0.45
Competitor quote + shock  threatening        0.02-0.10
```

**Why:** AI enrichment (CORTEX.COMPLETE) extracts churn signals from transcripts. If a customer with a 30% rate hike has a cheerful transcript, the AI won't flag churn language, the churn score stays low, and the customer never surfaces on the retention worklist. The structured data says "at risk" but the unstructured data says "happy" — and the model picks the wrong answer.

### 5. Seed customers who trip each guardrail

For every suppression rule, there must be at least one customer who would be recommended an action BUT gets suppressed. This validates that guardrails actually fire.

**Required guardrail test seeds:**

| Rule | What to seed |
|------|-------------|
| S01 Open-claim freeze | Customer with open claim + cross-sell eligibility (bundle gap) |
| S02 Litigation hold | Open claim + AT_FAULT + high reserves (>2x paid) |
| S03 Denial cooling-off | Claim denied within 90 days + cross-sell eligibility |
| S04 Collections | Billing in COLLECTIONS + cross-sell eligibility |
| S05 Active cancellation | CANCELLATION_REQUEST interaction within 14 days |
| S07 Minor | Customer under 18 with a policy |
| S09 Negative sentiment | Unresolved NEGATIVE interaction within 7 days |
| S10 Premium shock | PENDING_RENEWAL + rate shock flag + cross-sell eligibility |
| S11 Over-contact | 3+ outbound interactions within 14 days |
| S12 Do-not-contact | Interaction with topic DO_NOT_CONTACT |

**Why:** Without these, guardrail assertions pass vacuously (0 violations because 0 candidates to suppress). The hero CUST-00001 in the P&C demo naturally trips S01, S05, S09, and S10. Other rules need explicit test seeds.

## Workflow

### Step 1: Identify the domain

Determine the industry vertical. The bundled generator targets P&C insurance with these entities:

```
Household → Party → Policy → Claim
                  → Billing
                  → Interaction (phone transcripts, web, email)
                  → Quote
```

For other verticals, see [Retargeting Notes](#retargeting-notes).

### Step 2: Configure the generator

Key parameters in `gen_synth.py`:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `SEED` | 42 | Deterministic output for reproducibility |
| `TODAY` | `date.today()` | Anchor for all date offsets |
| `NUM_PARTIES` | 500 | Total customer count |
| `NUM_HOUSEHOLDS` | 310 | Household count (parties assigned round-robin) |

### Step 3: Generate and validate

```bash
python gen_synth.py      # → data/*.csv
python validate.py       # → PK uniqueness, FK integrity, hero spot checks
```

### Step 4: Load into Snowflake

```sql
-- Upload CSVs to stage
PUT file://data/*.csv @RAW.SEED_STAGE AUTO_COMPRESS=TRUE OVERWRITE=TRUE;

-- Load into RAW tables (idempotent: truncates first)
CALL RAW.SP_LOAD_SEED_DATA();
```

### Step 5: Verify hero storyline

After loading and running the downstream pipeline, verify the hero:

| Check | Expected |
|-------|----------|
| Churn risk score | > 0.40 (multiple signals firing) |
| Reason codes | 5+ codes including RATE_SHOCK, NEGATIVE_SENTIMENT |
| Recommended actions | Retention loyalty, supervisor rate review, stalled claim escalation |
| Suppressed actions | HOME_BUNDLE_CROSS_SELL suppressed by S01 (open claim) |
| Sentiment trajectory | Declining across call windows |

## Bundled Assets

| File | Purpose |
|------|---------|
| `assets/gen_synth.py` | Generator (P&C insurance, 960 lines) |
| `assets/validate.py` | PK/FK validator + hero spot checks |
| `assets/raw_ddl.sql` | Snowflake RAW table DDL + SP_LOAD_SEED_DATA |

## Retargeting Notes

### Lending (Consumer/Mortgage)

| Insurance entity | Lending equivalent | Key differences |
|------------------|--------------------|-----------------|
| Policy | Loan / Account | Status: CURRENT, DELINQUENT, DEFAULT, PAID_OFF |
| Claim | Dispute / Forbearance request | Status: OPEN, APPROVED, DENIED |
| Premium amount | Monthly payment / Outstanding balance | |
| Line of business | Product type (mortgage, auto loan, personal, credit card) | |
| Rate shock | Rate reset (ARM adjustment, promo-to-standard APR) | |
| Billing distress | Missed payments / 30-60-90 DPD buckets | |
| Bundle gap | Cross-sell: checking→savings, mortgage→HELOC, auto→refinance | |

**Hero storyline idea:** 10-year mortgage customer whose ARM resets from 3.5% to 7.2%, has a disputed late fee, and called 3 times with escalating frustration. Competitor is offering a fixed 5.8% refi.

**Guardrail adaptations:**
- S01 → Active dispute freeze (don't cross-sell during dispute)
- S02 → Default / charge-off hold (all outbound blocked)
- S04 → 60+ DPD (don't upsell while delinquent)

### Telecom (Mobile/Broadband)

| Insurance entity | Telecom equivalent | Key differences |
|------------------|-------------------|-----------------|
| Policy | Service plan / Subscription | Status: ACTIVE, SUSPENDED, CANCELLED |
| Claim | Service ticket / Network issue | Status: OPEN, RESOLVED, ESCALATED |
| Premium amount | Monthly recurring charge (MRC) | |
| Line of business | Product: mobile, broadband, TV, bundle | |
| Rate shock | Plan price increase / promo expiry | |
| Billing distress | Failed autopay / balance past due | |
| Bundle gap | Single-play → triple-play opportunity | |

**Hero storyline idea:** 8-year broadband customer whose plan price jumped 35% when the promo expired, has an unresolved network outage ticket open 3 weeks, and chatted twice about switching to a competitor offering the same speed for 40% less.

**Guardrail adaptations:**
- S01 → Active service ticket freeze (don't upsell during outage)
- S05 → Port-out request in progress
- S11 → Contact frequency particularly important (telecom has higher touch rates)
- New: Regulatory cooling-off period after contract renewal

## Stopping Points

- After Step 1 if vertical is not insurance (confirm entity mapping before generating)
- After Step 3 if validation fails (fix generator before loading)
- After Step 5 if hero story doesn't match expectations (re-examine purge/inject)

## Output

- `data/` directory with 7 CSV files (household, party, policy, claim, billing, interaction, quote)
- All CSVs referentially consistent (validated by `validate.py`)
- Hero customer with inspectable, compelling storyline
- Guardrail test seeds for every suppression rule
