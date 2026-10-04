# Plan: Nightly Pipeline Automation

## Context

CoCo Desktop automations cannot be registered on a trial account, so we'll implement this as a **Snowflake Task** on the same 2am IST schedule. The pipeline is:

1. **Enrichment** — `ENRICHED.INTERACTION_AI` is a regular table (630 rows, Cortex-processed). New transcripts in `CURATED.DT_INTERACTION` with `CHANNEL='PHONE'` that aren't yet in `INTERACTION_AI` need processing.
2. **Dynamic Table refresh** — `SERVING.CUSTOMER_360` and `SERVING.NBA_RECOMMENDATION` are DTs (TARGET_LAG 20min). We'll trigger an explicit `ALTER DYNAMIC TABLE ... REFRESH` to ensure they pick up the enrichment changes before validation runs.
3. **Guardrail assertions** — The critical one: no cross-sells to customers with open claims. Plus 4 more assertions covering litigation hold, reason codes, and collections. These must **fail loudly** (raise exceptions) so the task enters FAILED state and is visible in task history.

## CoCo automation fallback

CoCo Desktop does not support registered scheduled automations. The Snowflake Task approach gives us:
- CRON scheduling with timezone (`Asia/Kolkata`)
- Task history for monitoring (`TASK_HISTORY()`)
- Automatic failure propagation (exception = FAILED task run)
- `SUSPEND_TASK_AFTER_NUM_FAILURES` for circuit-breaking

---

## Step 1: SP_REFRESH_ENRICHMENT

Create `MERIDIAN.ENRICHED.SP_REFRESH_ENRICHMENT()` — a SQL stored procedure that:

- Finds phone interactions in `CURATED.DT_INTERACTION` not yet in `ENRICHED.INTERACTION_AI`
- For each, calls `SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4-5', prompt)` with the same JSON extraction prompt used during initial load
- Inserts results into `INTERACTION_AI` with the same parsing logic
- Returns a JSON object: `{ "new_transcripts": N, "parse_failures": M }`

If there are 0 new transcripts, it returns successfully with count 0 (no-op is fine).

## Step 2: SP_GUARDRAIL_CHECKS

Create `MERIDIAN.SERVING.SP_GUARDRAIL_CHECKS()` — the fail-loud assertion procedure:

| # | Assertion | Query | Fail condition |
|---|-----------|-------|----------------|
| G1 | No unsuppressed cross-sells to open-claim customers | Join NBA_RECOMMENDATION (STATUS='RECOMMENDED', CATEGORY='CROSS_SELL') with DT_CLAIM (CLAIM_STATUS IN ('OPEN','REOPENED')) | Count > 0 |
| G2 | No recommended actions under litigation hold | Join NBA_RECOMMENDATION (STATUS='RECOMMENDED') with DT_CLAIM (OPEN + AT_FAULT + high reserves) | Count > 0 |
| G3 | Every RECOMMENDED row has REASON_CODES | NBA_RECOMMENDATION WHERE STATUS='RECOMMENDED' AND (REASON_CODES IS NULL OR ARRAY_SIZE(REASON_CODES) = 0) | Count > 0 |
| G4 | Every RECOMMENDED row has REASON_TEXT | NBA_RECOMMENDATION WHERE STATUS='RECOMMENDED' AND REASON_TEXT IS NULL | Count > 0 |
| G5 | No cross-sell to COLLECTIONS customers | Join NBA_RECOMMENDATION (STATUS='RECOMMENDED', CATEGORY='CROSS_SELL') with DT_BILLING (BILLING_STATUS='COLLECTIONS') | Count > 0 |

Each assertion runs independently and its result is captured. If ANY assertion fails, the procedure raises an exception with a detailed message listing all failures. This makes the calling task enter FAILED state.

## Step 3: SP_NIGHTLY_PIPELINE

Create `MERIDIAN.APP.SP_NIGHTLY_PIPELINE()` — the orchestrator:

```
1. LET start_ts = CURRENT_TIMESTAMP()
2. CALL ENRICHED.SP_REFRESH_ENRICHMENT() → capture result
3. ALTER DYNAMIC TABLE SERVING.CUSTOMER_360 REFRESH
4. ALTER DYNAMIC TABLE SERVING.NBA_RECOMMENDATION REFRESH
5. CALL SERVING.SP_GUARDRAIL_CHECKS() → capture result (or let exception propagate)
6. Build JSON run report
7. RETURN run report
```

If step 5 raises, the exception propagates out of SP_NIGHTLY_PIPELINE, which makes the task fail. The task history will contain the error message with all failing assertion details.

## Step 4: Snowflake Task

```sql
CREATE OR REPLACE TASK MERIDIAN.APP.NIGHTLY_PIPELINE_REFRESH
  WAREHOUSE = MERIDIAN_WH
  SCHEDULE  = 'USING CRON 0 2 * * * Asia/Kolkata'
  SUSPEND_TASK_AFTER_NUM_FAILURES = 3
  COMMENT   = 'Meridian 360 nightly: enrich new transcripts, refresh DTs, validate guardrails'
AS
  CALL APP.SP_NIGHTLY_PIPELINE();

ALTER TASK MERIDIAN.APP.NIGHTLY_PIPELINE_REFRESH RESUME;
```

## Step 5: Evidence and local artifacts

- Write `coco-evidence/automations/nightly_pipeline.sql` containing all procedure and task DDL (reproducible from scratch)
- Append session entry to `coco-evidence/SESSIONS.md`
- Execute a manual test run of `SP_NIGHTLY_PIPELINE()` to verify it works before the first scheduled run

## Failure modes

| Scenario | Behavior |
|----------|----------|
| No new transcripts | Enrichment returns `{"new_transcripts": 0}`, DTs still refresh, guardrails still run |
| Cortex model unavailable | SP_REFRESH_ENRICHMENT raises → task FAILED |
| Cross-sell to open-claim customer leaks through | G1 assertion fails → SP_GUARDRAIL_CHECKS raises → task FAILED |
| 3 consecutive failures | Task auto-suspends (SUSPEND_TASK_AFTER_NUM_FAILURES = 3) |
