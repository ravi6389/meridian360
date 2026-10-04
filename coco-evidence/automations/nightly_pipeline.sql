/*=====================================================================
  Meridian 360 — Nightly Pipeline Automation
  Idempotent DDL for the 2am IST enrichment + validation pipeline.
  Created by CoCo session 2026-10-04.

  Objects created:
    ENRICHED.SP_REFRESH_ENRICHMENT()    — incremental transcript enrichment
    SERVING.SP_GUARDRAIL_CHECKS()       — 5 fail-loud guardrail assertions
    APP.SP_NIGHTLY_PIPELINE()           — orchestrator
    APP.NIGHTLY_PIPELINE_REFRESH        — Snowflake Task (CRON 0 2 * * * Asia/Kolkata)

  Prerequisites:
    GRANT EXECUTE TASK ON ACCOUNT TO ROLE MERIDIAN_BUILDER;   -- via ACCOUNTADMIN
=====================================================================*/

USE ROLE MERIDIAN_BUILDER;
USE WAREHOUSE MERIDIAN_WH;
USE DATABASE MERIDIAN;

-- ====================================================================
-- 1. SP_REFRESH_ENRICHMENT — incremental Cortex enrichment
--    Finds phone transcripts in CURATED.DT_INTERACTION not yet in
--    ENRICHED.INTERACTION_AI and processes them via claude-sonnet-4-5.
-- ====================================================================
CREATE OR REPLACE PROCEDURE ENRICHED.SP_REFRESH_ENRICHMENT()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
    LET new_count INTEGER := 0;
    LET fail_count INTEGER := 0;
    INSERT INTO MERIDIAN.ENRICHED.INTERACTION_AI
        (INTERACTION_ID, PARTY_ID, RAW_RESPONSE, PARSE_SUCCESS,
         AI_SENTIMENT_SCORE, AI_SENTIMENT_LABEL, AI_PRIMARY_INTENT,
         AI_CHURN_SIGNAL, AI_COMPLAINT_FLAG, AI_COMPETITOR_MENTIONED,
         AI_LIFE_EVENT, AI_PROMISED_CALLBACK, AI_RESOLVED_ON_CALL,
         AI_SUMMARY, AI_KEY_QUOTE, PROCESSED_AT)
    WITH new_transcripts AS (
        SELECT i.INTERACTION_ID, i.PARTY_ID, i.TRANSCRIPT_TEXT
        FROM MERIDIAN.CURATED.DT_INTERACTION i
        WHERE i.CHANNEL = 'PHONE'
          AND i.TRANSCRIPT_TEXT IS NOT NULL
          AND i.INTERACTION_ID NOT IN (
              SELECT INTERACTION_ID FROM MERIDIAN.ENRICHED.INTERACTION_AI
          )
    ),
    ai_raw AS (
        SELECT
            nt.INTERACTION_ID,
            nt.PARTY_ID,
            SNOWFLAKE.CORTEX.COMPLETE(
                'claude-sonnet-4-5',
                'You are an insurance call-center analyst. Analyse the following transcript and return ONLY a JSON object with these keys (no markdown, no explanation):\n'
                || '{"sentiment_score": <float 0-1, 1=positive>, "sentiment_label": "<POSITIVE|NEUTRAL|NEGATIVE>", '
                || '"primary_intent": "<string>", "churn_signal": <bool>, "complaint_flag": <bool>, '
                || '"competitor_mentioned": "<name or null>", "life_event": "<event or null>", '
                || '"promised_callback": <bool>, "resolved_on_call": <bool>, '
                || '"summary": "<1-2 sentence summary>", "key_quote": "<most significant verbatim quote>"}\n\n'
                || 'Transcript:\n' || nt.TRANSCRIPT_TEXT
            ) AS raw_response
        FROM new_transcripts nt
    ),
    parsed AS (
        SELECT
            ar.INTERACTION_ID,
            ar.PARTY_ID,
            ar.raw_response,
            TRY_PARSE_JSON(
                CASE
                    WHEN ar.raw_response LIKE '%```json%'
                    THEN REGEXP_SUBSTR(ar.raw_response, '```json\\s*(.+?)\\s*```', 1, 1, 's', 1)
                    WHEN ar.raw_response LIKE '%```%'
                    THEN REGEXP_SUBSTR(ar.raw_response, '```\\s*(.+?)\\s*```', 1, 1, 's', 1)
                    ELSE ar.raw_response
                END
            ) AS j
        FROM ai_raw ar
    )
    SELECT
        p.INTERACTION_ID,
        p.PARTY_ID,
        p.raw_response,
        (p.j IS NOT NULL)                              AS PARSE_SUCCESS,
        p.j:"sentiment_score"::NUMBER(5,4)             AS AI_SENTIMENT_SCORE,
        p.j:"sentiment_label"::VARCHAR                 AS AI_SENTIMENT_LABEL,
        p.j:"primary_intent"::VARCHAR                  AS AI_PRIMARY_INTENT,
        p.j:"churn_signal"::BOOLEAN                    AS AI_CHURN_SIGNAL,
        p.j:"complaint_flag"::BOOLEAN                  AS AI_COMPLAINT_FLAG,
        NULLIF(p.j:"competitor_mentioned"::VARCHAR, 'null') AS AI_COMPETITOR_MENTIONED,
        NULLIF(p.j:"life_event"::VARCHAR, 'null')      AS AI_LIFE_EVENT,
        p.j:"promised_callback"::BOOLEAN               AS AI_PROMISED_CALLBACK,
        p.j:"resolved_on_call"::BOOLEAN                AS AI_RESOLVED_ON_CALL,
        p.j:"summary"::VARCHAR                         AS AI_SUMMARY,
        p.j:"key_quote"::VARCHAR                       AS AI_KEY_QUOTE,
        CURRENT_TIMESTAMP()                             AS PROCESSED_AT
    FROM parsed p;
    new_count := SQLROWCOUNT;
    SELECT COUNT(*) INTO :fail_count
    FROM MERIDIAN.ENRICHED.INTERACTION_AI
    WHERE PARSE_SUCCESS = FALSE
      AND PROCESSED_AT >= DATEADD('minute', -5, CURRENT_TIMESTAMP());
    RETURN OBJECT_CONSTRUCT(
        'new_transcripts', :new_count,
        'parse_failures', :fail_count,
        'status', IFF(:fail_count > 0, 'WARNING', 'OK')
    );
END;
$$;


-- ====================================================================
-- 2. SP_GUARDRAIL_CHECKS — 5 assertions, returns report VARIANT
--    G1: No cross-sells to open-claim customers (S01 enforcement)
--    G2: No actions for litigation-hold customers (S02 enforcement)
--    G3: Every recommendation has evidence (Rule 6)
--    G4: Every recommendation has REASON_TEXT
--    G5: No cross-sells to COLLECTIONS customers (S04 enforcement)
-- ====================================================================
CREATE OR REPLACE PROCEDURE SERVING.SP_GUARDRAIL_CHECKS()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    g1_count INTEGER;
    g2_count INTEGER;
    g3_count INTEGER;
    g4_count INTEGER;
    g5_count INTEGER;
    fail_list ARRAY DEFAULT ARRAY_CONSTRUCT();
BEGIN
    SELECT COUNT(*) INTO :g1_count
    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION r
    JOIN MERIDIAN.CURATED.DT_CLAIM cl
      ON r.PARTY_ID = cl.PARTY_ID AND cl.CLAIM_STATUS IN ('OPEN', 'REOPENED')
    WHERE r.STATUS = 'RECOMMENDED' AND r.CATEGORY = 'CROSS_SELL';
    IF (g1_count > 0) THEN
        fail_list := ARRAY_APPEND(:fail_list, 'G1: ' || :g1_count || ' cross-sells to open-claim customers');
    END IF;

    SELECT COUNT(*) INTO :g2_count
    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION r
    JOIN MERIDIAN.CURATED.DT_CLAIM cl
      ON r.PARTY_ID = cl.PARTY_ID AND cl.CLAIM_STATUS = 'OPEN'
     AND cl.FAULT_INDICATOR = 'AT_FAULT' AND cl.RESERVE_AMOUNT > cl.PAID_AMOUNT * 2
    WHERE r.STATUS = 'RECOMMENDED';
    IF (g2_count > 0) THEN
        fail_list := ARRAY_APPEND(:fail_list, 'G2: ' || :g2_count || ' actions for litigation-hold customers');
    END IF;

    SELECT COUNT(*) INTO :g3_count
    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION
    WHERE STATUS = 'RECOMMENDED'
      AND (REASON_CODES IS NULL OR ARRAY_SIZE(REASON_CODES) = 0);
    IF (g3_count > 0) THEN
        fail_list := ARRAY_APPEND(:fail_list, 'G3: ' || :g3_count || ' recommendations missing REASON_CODES');
    END IF;

    SELECT COUNT(*) INTO :g4_count
    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION
    WHERE STATUS = 'RECOMMENDED' AND REASON_TEXT IS NULL;
    IF (g4_count > 0) THEN
        fail_list := ARRAY_APPEND(:fail_list, 'G4: ' || :g4_count || ' recommendations missing REASON_TEXT');
    END IF;

    SELECT COUNT(*) INTO :g5_count
    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION r
    JOIN MERIDIAN.CURATED.DT_BILLING b
      ON r.PARTY_ID = b.PARTY_ID AND b.BILLING_STATUS = 'COLLECTIONS'
    WHERE r.STATUS = 'RECOMMENDED' AND r.CATEGORY = 'CROSS_SELL';
    IF (g5_count > 0) THEN
        fail_list := ARRAY_APPEND(:fail_list, 'G5: ' || :g5_count || ' cross-sells to COLLECTIONS customers');
    END IF;

    RETURN OBJECT_CONSTRUCT(
        'g1_open_claim_cross_sell',  OBJECT_CONSTRUCT('violations', :g1_count, 'pass', :g1_count = 0),
        'g2_litigation_hold',        OBJECT_CONSTRUCT('violations', :g2_count, 'pass', :g2_count = 0),
        'g3_missing_reason_codes',   OBJECT_CONSTRUCT('violations', :g3_count, 'pass', :g3_count = 0),
        'g4_missing_reason_text',    OBJECT_CONSTRUCT('violations', :g4_count, 'pass', :g4_count = 0),
        'g5_collections_cross_sell', OBJECT_CONSTRUCT('violations', :g5_count, 'pass', :g5_count = 0),
        'failures', :fail_list,
        'total_failures', ARRAY_SIZE(:fail_list),
        'all_passed', ARRAY_SIZE(:fail_list) = 0
    );
END;
$$;


-- ====================================================================
-- 3. SP_NIGHTLY_PIPELINE — orchestrator
--    Enrichment → DT refresh → guardrails → fail loud
-- ====================================================================
CREATE OR REPLACE PROCEDURE APP.SP_NIGHTLY_PIPELINE()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    start_ts TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP();
    enrich_result VARIANT;
    guardrail_result VARIANT;
    all_passed BOOLEAN;
    report VARCHAR;
    guardrail_failure EXCEPTION (-20001, 'GUARDRAIL_ASSERTION_FAILURE');
BEGIN
    CALL MERIDIAN.ENRICHED.SP_REFRESH_ENRICHMENT() INTO :enrich_result;
    ALTER DYNAMIC TABLE MERIDIAN.SERVING.CUSTOMER_360 REFRESH;
    ALTER DYNAMIC TABLE MERIDIAN.SERVING.NBA_RECOMMENDATION REFRESH;
    CALL MERIDIAN.SERVING.SP_GUARDRAIL_CHECKS() INTO :guardrail_result;
    all_passed := guardrail_result:"all_passed"::BOOLEAN;
    report := OBJECT_CONSTRUCT(
        'run_start', :start_ts,
        'run_end', CURRENT_TIMESTAMP(),
        'enrichment', :enrich_result,
        'guardrails', :guardrail_result,
        'status', IFF(:all_passed, 'SUCCESS', 'GUARDRAIL_FAILURE')
    )::VARCHAR;
    BEGIN
        CALL SYSTEM$SET_RETURN_VALUE(:report);
    EXCEPTION
        WHEN OTHER THEN NULL;
    END;
    IF (NOT all_passed) THEN
        RAISE guardrail_failure;
    END IF;
    RETURN :report;
END;
$$;


-- ====================================================================
-- 4. Snowflake Task — 2am IST nightly
-- ====================================================================
-- Prerequisite (run as ACCOUNTADMIN):
--   GRANT EXECUTE TASK ON ACCOUNT TO ROLE MERIDIAN_BUILDER;

CREATE OR REPLACE TASK APP.NIGHTLY_PIPELINE_REFRESH
  WAREHOUSE = MERIDIAN_WH
  SCHEDULE  = 'USING CRON 0 2 * * * Asia/Kolkata'
  SUSPEND_TASK_AFTER_NUM_FAILURES = 3
  COMMENT   = 'Meridian 360 nightly: enrich new transcripts, refresh DTs, validate guardrails. Fails loud on assertion violation.'
AS
  CALL MERIDIAN.APP.SP_NIGHTLY_PIPELINE();

ALTER TASK APP.NIGHTLY_PIPELINE_REFRESH RESUME;


-- ====================================================================
-- Monitoring: check task history
-- ====================================================================
-- SELECT name, state, scheduled_time, return_value, error_code, error_message
--   FROM TABLE(SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY(
--     TASK_NAME => 'NIGHTLY_PIPELINE_REFRESH',
--     SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
--   ))
--   WHERE database_name = 'MERIDIAN' AND schema_name = 'APP'
--   ORDER BY scheduled_time DESC;
