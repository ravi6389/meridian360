/*=====================================================================
  Meridian 360 — 05_serving.sql
  Serving layer: Customer 360, timeline, household bundle gaps.
  CUSTOMER_360 includes a transparent weighted-additive churn model
  where every term is an inspectable column and feeds reason codes.
  Idempotent — CREATE OR REPLACE.
=====================================================================*/

USE ROLE MERIDIAN_BUILDER;
USE WAREHOUSE MERIDIAN_WH;
USE DATABASE MERIDIAN;

-- ====================================================================
-- ENRICHMENT STUB — placeholder for AI-derived signals.
-- Replace with a real dynamic table when sql/04_enrichment.sql is built.
-- The CUSTOMER_360 LEFT JOINs here; NULLs coalesce to 0.
-- ====================================================================
CREATE OR REPLACE VIEW ENRICHED.V_AI_SIGNALS AS
SELECT
    PARTY_ID,
    NULL::NUMBER(5,4)  AS AI_CHURN_LANGUAGE_SCORE,
    NULL::NUMBER(5,4)  AS AI_COMPETITOR_MENTION_SCORE
FROM RAW.PARTY;

-- ====================================================================
-- CUSTOMER_360 — one row per customer, all signals + churn score
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE SERVING.CUSTOMER_360
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
WITH
-- ── Per-customer aggregates ─────────────────────────────────────────
policy_agg AS (
    SELECT
        PARTY_ID,
        COUNT(*)                              AS POLICY_COUNT,
        COUNT(DISTINCT LINE_OF_BUSINESS)      AS LOB_COUNT,
        ARRAY_AGG(DISTINCT LINE_OF_BUSINESS)
            WITHIN GROUP (ORDER BY LINE_OF_BUSINESS) AS LOBS_HELD,
        SUM(PREMIUM_AMOUNT)                   AS TOTAL_PREMIUM,
        MIN(DAYS_TO_RENEWAL)                  AS NEAREST_RENEWAL_DAYS,
        MAX(RATE_SHOCK_FLAG::INT)             AS HAS_RATE_SHOCK
    FROM CURATED.DT_POLICY
    WHERE STATUS IN ('ACTIVE', 'PENDING_RENEWAL')
    GROUP BY PARTY_ID
),
claim_agg AS (
    SELECT
        PARTY_ID,
        COUNT(*)                                                         AS TOTAL_CLAIMS,
        SUM(CASE WHEN CLAIM_STATUS IN ('OPEN','REOPENED') THEN 1 ELSE 0 END) AS OPEN_CLAIMS,
        MAX(CASE WHEN UNRESOLVED_FLAG THEN 1 ELSE 0 END)                AS HAS_UNRESOLVED_CLAIM,
        MAX(CASE WHEN CLAIM_STATUS = 'DENIED' THEN 1 ELSE 0 END)        AS HAS_DENIED_CLAIM,
        MAX(DAYS_OPEN)                                                   AS MAX_CLAIM_DAYS_OPEN,
        SUM(RESERVE_AMOUNT)                                              AS TOTAL_RESERVES,
        SUM(PAID_AMOUNT)                                                 AS TOTAL_CLAIM_PAID
    FROM CURATED.DT_CLAIM
    GROUP BY PARTY_ID
),
billing_agg AS (
    SELECT
        PARTY_ID,
        SUM(CASE WHEN PAYMENT_DISTRESS_FLAG THEN 1 ELSE 0 END) AS DISTRESSED_BILLS,
        MAX(CASE WHEN PAYMENT_DISTRESS_FLAG THEN 1 ELSE 0 END) AS HAS_PAYMENT_DISTRESS,
        MAX(DAYS_PAST_DUE)                                      AS MAX_DAYS_PAST_DUE,
        SUM(AMOUNT_DUE)                                          AS TOTAL_BILLED,
        SUM(AMOUNT_PAID)                                         AS TOTAL_BILLING_PAID
    FROM CURATED.DT_BILLING
    GROUP BY PARTY_ID
),
web_agg AS (
    SELECT
        PARTY_ID,
        COUNT(*)  AS WEB_SESSIONS,
        SUM(CASE WHEN RISK_PAGE_FLAG
                  AND INTERACTION_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                 THEN 1 ELSE 0 END)  AS RECENT_RISK_PAGES,
        SUM(CASE WHEN TOPIC = 'CANCELLATION_PAGE'
                  AND INTERACTION_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                 THEN 1 ELSE 0 END)  AS RECENT_CANCEL_PAGES
    FROM CURATED.DT_WEB_SESSION
    GROUP BY PARTY_ID
),
call_sentiment AS (
    SELECT
        PARTY_ID,
        AVG(CASE WHEN INTERACTION_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                 THEN SENTIMENT_SCORE END)  AS RECENT_30D_SENTIMENT,
        AVG(CASE WHEN INTERACTION_DATE >= DATEADD('day', -60, CURRENT_TIMESTAMP())
                  AND INTERACTION_DATE <  DATEADD('day', -30, CURRENT_TIMESTAMP())
                 THEN SENTIMENT_SCORE END)  AS PRIOR_30D_SENTIMENT,
        COUNT(CASE WHEN SENTIMENT = 'NEGATIVE'
                    AND INTERACTION_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                   THEN 1 END)              AS RECENT_NEGATIVE_CALLS,
        COUNT(*)                             AS TOTAL_CALLS
    FROM CURATED.DT_INTERACTION
    WHERE CHANNEL = 'PHONE'
    GROUP BY PARTY_ID
),
quote_agg AS (
    SELECT
        PARTY_ID,
        COUNT(*)             AS QUOTE_COUNT,
        MIN(QUOTED_PREMIUM)  AS MIN_QUOTED_PREMIUM
    FROM CURATED.DT_QUOTE
    WHERE PARTY_ID IS NOT NULL
    GROUP BY PARTY_ID
),

-- ── Join everything, compute signal terms ───────────────────────────
scored AS (
    SELECT
        -- Customer base
        c.PARTY_ID, c.FIRST_NAME, c.LAST_NAME, c.DATE_OF_BIRTH,
        c.EMAIL, c.PHONE, c.STATE, c.HOUSEHOLD_ID,
        c.HOUSEHOLD_MEMBER_COUNT, c.TENURE_YEARS, c.AGE,

        -- Policy aggregates
        COALESCE(pa.POLICY_COUNT, 0)        AS POLICY_COUNT,
        COALESCE(pa.LOB_COUNT, 0)           AS LOB_COUNT,
        pa.LOBS_HELD,
        COALESCE(pa.TOTAL_PREMIUM, 0)       AS TOTAL_PREMIUM,
        pa.NEAREST_RENEWAL_DAYS,

        -- Claim aggregates
        COALESCE(ca.TOTAL_CLAIMS, 0)        AS TOTAL_CLAIMS,
        COALESCE(ca.OPEN_CLAIMS, 0)         AS OPEN_CLAIMS,
        ca.MAX_CLAIM_DAYS_OPEN,

        -- Billing aggregates
        COALESCE(ba.DISTRESSED_BILLS, 0)    AS DISTRESSED_BILLS,
        ba.MAX_DAYS_PAST_DUE,

        -- Digital aggregates
        COALESCE(wa.WEB_SESSIONS, 0)        AS WEB_SESSIONS,
        COALESCE(wa.RECENT_RISK_PAGES, 0)   AS RECENT_RISK_PAGES,
        COALESCE(wa.RECENT_CANCEL_PAGES, 0) AS RECENT_CANCEL_PAGES,

        -- Sentiment aggregates
        cs.RECENT_30D_SENTIMENT,
        cs.PRIOR_30D_SENTIMENT,
        COALESCE(cs.RECENT_NEGATIVE_CALLS, 0) AS RECENT_NEGATIVE_CALLS,
        COALESCE(cs.TOTAL_CALLS, 0)           AS TOTAL_CALLS,

        -- Quotes
        COALESCE(qa.QUOTE_COUNT, 0)         AS QUOTE_COUNT,

        -- ═══════════ CHURN SIGNAL TERMS (each 0–1) ═══════════

        -- S1: Recent negative sentiment
        CASE WHEN cs.RECENT_30D_SENTIMENT IS NOT NULL
                  AND cs.RECENT_30D_SENTIMENT < 0.30 THEN 1.0
             WHEN cs.RECENT_30D_SENTIMENT IS NOT NULL
                  AND cs.RECENT_30D_SENTIMENT < 0.45 THEN 0.5
             ELSE 0.0
        END AS SIG_NEGATIVE_SENTIMENT,

        -- S2: Declining sentiment trajectory (recent vs prior window)
        CASE WHEN cs.RECENT_30D_SENTIMENT IS NOT NULL
              AND cs.PRIOR_30D_SENTIMENT  IS NOT NULL
              AND cs.RECENT_30D_SENTIMENT < cs.PRIOR_30D_SENTIMENT - 0.10
             THEN 1.0
             ELSE 0.0
        END AS SIG_DECLINING_TRAJECTORY,

        -- S3: Explicit churn language (AI-derived, null-tolerant)
        COALESCE(e.AI_CHURN_LANGUAGE_SCORE, 0)     AS SIG_CHURN_LANGUAGE,

        -- S4: Competitor mentions (AI-derived, null-tolerant)
        COALESCE(e.AI_COMPETITOR_MENTION_SCORE, 0)  AS SIG_COMPETITOR_MENTION,

        -- S5: Cancellation page views in last 30 days
        CASE WHEN COALESCE(wa.RECENT_CANCEL_PAGES, 0) >= 2 THEN 1.0
             WHEN COALESCE(wa.RECENT_CANCEL_PAGES, 0) >= 1 THEN 0.5
             ELSE 0.0
        END AS SIG_CANCELLATION_PAGES,

        -- S6: Rate shock (pending renewal + competitor undercuts by >15%)
        CASE WHEN COALESCE(pa.HAS_RATE_SHOCK, 0) = 1 THEN 1.0
             ELSE 0.0
        END AS SIG_RATE_SHOCK,

        -- S7: Disputed/unresolved claims
        CASE WHEN COALESCE(ca.HAS_UNRESOLVED_CLAIM, 0) = 1 THEN 1.0
             WHEN COALESCE(ca.HAS_DENIED_CLAIM, 0)    = 1 THEN 0.8
             ELSE 0.0
        END AS SIG_DISPUTED_CLAIMS,

        -- S8: Payment distress
        CASE WHEN COALESCE(ba.HAS_PAYMENT_DISTRESS, 0) = 1 THEN 1.0
             ELSE 0.0
        END AS SIG_PAYMENT_DISTRESS,

        -- S9: Mono-line household (no bundle lock-in)
        CASE WHEN COALESCE(pa.LOB_COUNT, 0) <= 1 THEN 1.0
             ELSE 0.0
        END AS SIG_MONO_LINE,

        -- Tenure dampener: long tenure reduces churn propensity
        -- f(t) = 1 / (1 + ln(1 + t)),  t=0 → 1.0,  t=5 → 0.56,  t=12 → 0.38
        1.0 / (1.0 + LN(1.0 + GREATEST(c.TENURE_YEARS, 0)))
            AS TENURE_DAMPENER

    FROM CURATED.DT_CUSTOMER      c
    LEFT JOIN policy_agg          pa ON c.PARTY_ID = pa.PARTY_ID
    LEFT JOIN claim_agg           ca ON c.PARTY_ID = ca.PARTY_ID
    LEFT JOIN billing_agg         ba ON c.PARTY_ID = ba.PARTY_ID
    LEFT JOIN web_agg             wa ON c.PARTY_ID = wa.PARTY_ID
    LEFT JOIN call_sentiment      cs ON c.PARTY_ID = cs.PARTY_ID
    LEFT JOIN quote_agg           qa ON c.PARTY_ID = qa.PARTY_ID
    LEFT JOIN ENRICHED.V_AI_SIGNALS e ON c.PARTY_ID = e.PARTY_ID
)

-- ── Final select: score + reason codes ──────────────────────────────
SELECT
    s.*,

    -- Weighted additive churn score, clamped [0, 1]
    -- Weights sum to 1.0 before the tenure dampener is applied.
    LEAST(1.0, GREATEST(0.0,
      ( 0.15 * SIG_NEGATIVE_SENTIMENT
      + 0.08 * SIG_DECLINING_TRAJECTORY
      + 0.12 * SIG_CHURN_LANGUAGE
      + 0.08 * SIG_COMPETITOR_MENTION
      + 0.12 * SIG_CANCELLATION_PAGES
      + 0.15 * SIG_RATE_SHOCK
      + 0.12 * SIG_DISPUTED_CLAIMS
      + 0.10 * SIG_PAYMENT_DISTRESS
      + 0.08 * SIG_MONO_LINE
      ) * TENURE_DAMPENER
    ))::NUMBER(5,4)  AS CHURN_RISK_SCORE,

    -- Reason codes: array of every active signal
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        IFF(SIG_NEGATIVE_SENTIMENT    > 0, 'NEGATIVE_SENTIMENT',    NULL),
        IFF(SIG_DECLINING_TRAJECTORY  > 0, 'DECLINING_SENTIMENT',   NULL),
        IFF(SIG_CHURN_LANGUAGE        > 0, 'CHURN_LANGUAGE',        NULL),
        IFF(SIG_COMPETITOR_MENTION    > 0, 'COMPETITOR_MENTION',    NULL),
        IFF(SIG_CANCELLATION_PAGES    > 0, 'CANCELLATION_BROWSING', NULL),
        IFF(SIG_RATE_SHOCK            > 0, 'RATE_SHOCK',            NULL),
        IFF(SIG_DISPUTED_CLAIMS       > 0, 'DISPUTED_CLAIM',        NULL),
        IFF(SIG_PAYMENT_DISTRESS      > 0, 'PAYMENT_DISTRESS',      NULL),
        IFF(SIG_MONO_LINE             > 0, 'MONO_LINE_HOUSEHOLD',   NULL)
    )) AS CHURN_REASON_CODES

FROM scored s;


-- ====================================================================
-- CUSTOMER_TIMELINE — unified event stream across all domains
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE SERVING.CUSTOMER_TIMELINE
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS

-- Policy: bound
SELECT PARTY_ID,
       EFFECTIVE_DATE::TIMESTAMP_NTZ                          AS EVENT_TS,
       'POLICY_BOUND'                                         AS EVENT_TYPE,
       'POLICY'                                               AS CATEGORY,
       LINE_OF_BUSINESS || ' policy ' || POLICY_ID || ' bound, premium ' || PREMIUM_AMOUNT
                                                              AS DESCRIPTION,
       POLICY_ID                                              AS RELATED_ID
FROM CURATED.DT_POLICY

UNION ALL

-- Policy: renewal due
SELECT PARTY_ID,
       EXPIRATION_DATE::TIMESTAMP_NTZ,
       'RENEWAL_DUE', 'POLICY',
       LINE_OF_BUSINESS || ' policy ' || POLICY_ID || ' renewal due'
         || IFF(RATE_SHOCK_FLAG, ' [RATE SHOCK]', ''),
       POLICY_ID
FROM CURATED.DT_POLICY
WHERE STATUS IN ('ACTIVE', 'PENDING_RENEWAL')

UNION ALL

-- Policy: cancelled
SELECT PARTY_ID,
       CANCELLATION_DATE::TIMESTAMP_NTZ,
       'POLICY_CANCELLED', 'POLICY',
       LINE_OF_BUSINESS || ' policy ' || POLICY_ID || ' cancelled',
       POLICY_ID
FROM CURATED.DT_POLICY
WHERE CANCELLATION_DATE IS NOT NULL

UNION ALL

-- Claim: filed
SELECT PARTY_ID,
       REPORT_DATE::TIMESTAMP_NTZ,
       'CLAIM_FILED', 'CLAIM',
       CLAIM_TYPE || ' claim ' || CLAIM_ID || ' filed'
         || IFF(FAULT_INDICATOR = 'NOT_AT_FAULT', ' (not at fault)', ''),
       CLAIM_ID
FROM CURATED.DT_CLAIM

UNION ALL

-- Billing: due / distressed
SELECT PARTY_ID,
       DUE_DATE::TIMESTAMP_NTZ,
       IFF(PAYMENT_DISTRESS_FLAG, 'PAYMENT_MISSED', 'PAYMENT_DUE'),
       'BILLING',
       'Payment ' || BILLING_ID || ': ' || AMOUNT_DUE
         || CASE BILLING_STATUS
              WHEN 'PAID'        THEN ' (paid)'
              WHEN 'PAST_DUE'    THEN ' (PAST DUE)'
              WHEN 'COLLECTIONS' THEN ' (COLLECTIONS)'
              ELSE '' END,
       BILLING_ID
FROM CURATED.DT_BILLING

UNION ALL

-- Interactions: all channels
SELECT PARTY_ID,
       INTERACTION_DATE,
       CHANNEL || '_' || COALESCE(TOPIC, 'OTHER'),
       'INTERACTION',
       COALESCE(SUMMARY, CHANNEL || ' interaction: ' || TOPIC),
       INTERACTION_ID
FROM CURATED.DT_INTERACTION

UNION ALL

-- Web sessions (separate from interactions for risk-page annotation)
SELECT PARTY_ID,
       INTERACTION_DATE,
       'WEB_' || TOPIC,
       'DIGITAL',
       SUMMARY || IFF(RISK_PAGE_FLAG, ' [RISK PAGE]', ''),
       INTERACTION_ID
FROM CURATED.DT_WEB_SESSION

UNION ALL

-- Quotes
SELECT PARTY_ID,
       QUOTE_DATE::TIMESTAMP_NTZ,
       'QUOTE_' || QUOTE_STATUS,
       'QUOTE',
       LINE_OF_BUSINESS || ' quote ' || QUOTE_ID || ': ' || QUOTED_PREMIUM
         || ' via ' || SOURCE,
       QUOTE_ID
FROM CURATED.DT_QUOTE
WHERE PARTY_ID IS NOT NULL;


-- ====================================================================
-- V_HOUSEHOLD_BUNDLE_GAP — identifies cross-sell opportunities
-- ====================================================================
CREATE OR REPLACE VIEW SERVING.V_HOUSEHOLD_BUNDLE_GAP AS
WITH household_lobs AS (
    SELECT
        c.HOUSEHOLD_ID,
        ARRAY_AGG(DISTINCT p.LINE_OF_BUSINESS)
            WITHIN GROUP (ORDER BY p.LINE_OF_BUSINESS) AS LOBS_HELD,
        COUNT(DISTINCT p.LINE_OF_BUSINESS)             AS LOB_COUNT,
        COUNT(DISTINCT c.PARTY_ID)                     AS MEMBER_COUNT,
        MAX(IFF(p.LINE_OF_BUSINESS = 'AUTO',     1, 0)) AS HAS_AUTO,
        MAX(IFF(p.LINE_OF_BUSINESS = 'HOME',     1, 0)) AS HAS_HOME,
        MAX(IFF(p.LINE_OF_BUSINESS = 'UMBRELLA', 1, 0)) AS HAS_UMBRELLA,
        MAX(IFF(p.LINE_OF_BUSINESS = 'RENTERS',  1, 0)) AS HAS_RENTERS,
        SUM(p.PREMIUM_AMOUNT)                            AS HOUSEHOLD_PREMIUM
    FROM CURATED.DT_CUSTOMER c
    LEFT JOIN CURATED.DT_POLICY p
      ON  c.PARTY_ID = p.PARTY_ID
      AND p.STATUS IN ('ACTIVE', 'PENDING_RENEWAL')
    GROUP BY c.HOUSEHOLD_ID
)
SELECT
    HOUSEHOLD_ID,
    LOBS_HELD,
    LOB_COUNT,
    MEMBER_COUNT,
    HAS_AUTO, HAS_HOME, HAS_UMBRELLA, HAS_RENTERS,
    HOUSEHOLD_PREMIUM,
    -- Gap flags
    HAS_AUTO  = 1 AND HAS_HOME = 0       AS GAP_NEEDS_HOME,
    HAS_HOME  = 1 AND HAS_AUTO = 0       AS GAP_NEEDS_AUTO,
    LOB_COUNT >= 2  AND HAS_UMBRELLA = 0  AS GAP_NEEDS_UMBRELLA,
    -- Primary cross-sell opportunity
    CASE
      WHEN HAS_AUTO = 1 AND HAS_HOME = 0 THEN 'HOME'
      WHEN HAS_HOME = 1 AND HAS_AUTO = 0 THEN 'AUTO'
      WHEN LOB_COUNT >= 2 AND HAS_UMBRELLA = 0 THEN 'UMBRELLA'
      ELSE NULL
    END AS PRIMARY_CROSS_SELL_LOB
FROM household_lobs;
