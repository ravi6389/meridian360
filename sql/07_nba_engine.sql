/*=====================================================================
  Meridian 360 — 07_nba_engine.sql
  Next Best Action engine: catalog, candidate generation, suppression,
  recommendation ranking, action log, and audit view.
  Idempotent — CREATE OR REPLACE for views/DTs, IF NOT EXISTS for tables.
=====================================================================*/

USE ROLE MERIDIAN_BUILDER;
USE WAREHOUSE MERIDIAN_WH;
USE DATABASE MERIDIAN;

-- ====================================================================
-- 1. ACTION CATALOG — the menu of things the business will do
-- ====================================================================
CREATE OR REPLACE TABLE SERVING.ACTION_CATALOG (
    ACTION_TYPE          VARCHAR   NOT NULL,
    ACTION_NAME          VARCHAR   NOT NULL,
    CATEGORY             VARCHAR   NOT NULL,  -- RETENTION / CROSS_SELL / SERVICE / RISK
    CHANNEL              VARCHAR,             -- PHONE / EMAIL / IN_APP / SYSTEM
    EV_SHARE_OF_PREMIUM  NUMBER(5,4),         -- expected value as share of premium at risk
    COST_TO_SERVE        NUMBER(12,2),
    NEEDS_SUPERVISOR     BOOLEAN   DEFAULT FALSE,
    SUPERVISOR_THRESHOLD VARCHAR,             -- condition requiring approval
    SLA_DAYS             NUMBER,
    DESCRIPTION          VARCHAR,
    CONSTRAINT PK_ACTION_CATALOG PRIMARY KEY (ACTION_TYPE)
);

INSERT OVERWRITE INTO SERVING.ACTION_CATALOG VALUES
('RETENTION_LOYALTY_CREDIT',  'Retention Loyalty Credit',          'RETENTION',   'EMAIL',    0.08, 500.00,  FALSE, NULL,                                          3,  'Offer loyalty discount or credit to high-value at-risk customer to retain the policy.'),
('SUPERVISOR_RATE_REVIEW',    'Supervisor Rate Review',            'RETENTION',   'PHONE',    0.12, 200.00,  TRUE,  'Premium increase > 15% on pending renewal',    2,  'Escalate to supervisor for manual rate review when algorithmic increase exceeds threshold.'),
('STALLED_CLAIM_ESCALATION',  'Stalled Claim Escalation',         'SERVICE',     'SYSTEM',   0.06, 100.00,  FALSE, NULL,                                          1,  'Escalate open claim stalled beyond SLA to claims manager for resolution.'),
('HONOUR_CALLBACK',           'Honour Outstanding Callback',       'SERVICE',     'PHONE',    0.03, 50.00,   FALSE, NULL,                                          1,  'Fulfil a promised callback that was never completed, restoring trust.'),
('HOME_BUNDLE_CROSS_SELL',    'Home Bundle Cross-Sell',            'CROSS_SELL',  'EMAIL',    0.15, 300.00,  FALSE, NULL,                                          7,  'Offer home insurance to auto-only household to create bundle stickiness.'),
('BILLING_MANDATE_REPAIR',    'Billing Mandate Repair',            'SERVICE',     'PHONE',    0.04, 75.00,   FALSE, NULL,                                          2,  'Contact customer with payment issues to repair billing mandate and prevent lapse.'),
('PROACTIVE_WINBACK',         'Proactive Win-Back Outreach',       'RETENTION',   'PHONE',    0.10, 400.00,  TRUE,  'Customer has competitor quote or churn language', 5,  'Proactive outreach to customer showing competitive shopping or explicit churn signals.');


-- ====================================================================
-- 2. SUPPRESSION VIEW — 12 rules from docs/architecture.md
--    One row per (PARTY_ID, ACTION_TYPE, RULE_ID).
--    Suppressed actions are visible but never recommended.
-- ====================================================================
CREATE OR REPLACE VIEW SERVING.V_SUPPRESSION AS

-- S01: Open-claim freeze → blocks CROSS_SELL, UPSELL, RENEWAL offers
SELECT DISTINCT
    c.PARTY_ID,
    a.ACTION_TYPE,
    'S01'              AS RULE_ID,
    'Open-claim freeze' AS RULE_NAME,
    'Customer has an open or reopened claim — cannot solicit new products' AS REASON,
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS SUPPRESSED_AT,
    NULL::TIMESTAMP_NTZ AS EXPIRES_AT
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_CLAIM cl ON c.PARTY_ID = cl.PARTY_ID
    AND cl.CLAIM_STATUS IN ('OPEN', 'REOPENED')
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL')

UNION ALL

-- S02: Litigation hold → blocks ALL outbound
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S02', 'Litigation hold',
    'At-fault open claim with high reserves — potential litigation, all outbound blocked',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_CLAIM cl ON c.PARTY_ID = cl.PARTY_ID
    AND cl.CLAIM_STATUS = 'OPEN'
    AND cl.FAULT_INDICATOR = 'AT_FAULT'
    AND cl.RESERVE_AMOUNT > cl.PAID_AMOUNT * 2
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a

UNION ALL

-- S03: Recent denial cooling-off → blocks CROSS_SELL
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S03', 'Recent denial cooling-off',
    'Claim denied within last 90 days — selling new coverage is insensitive',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_CLAIM cl ON c.PARTY_ID = cl.PARTY_ID
    AND cl.CLAIM_STATUS = 'DENIED'
    AND cl.REPORT_DATE >= DATEADD('day', -90, CURRENT_DATE())
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL')

UNION ALL

-- S04: Collections status → blocks CROSS_SELL, RETENTION loyalty
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S04', 'Collections status',
    'Customer has billing in collections — marketing prohibited',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_BILLING b ON c.PARTY_ID = b.PARTY_ID
    AND b.BILLING_STATUS = 'COLLECTIONS'
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL') OR a.ACTION_TYPE = 'RETENTION_LOYALTY_CREDIT'

UNION ALL

-- S05: Cancellation in progress → blocks CROSS_SELL
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S05', 'Cancellation in progress',
    'Customer has active cancellation request — resolve root cause first',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_INTERACTION i ON c.PARTY_ID = i.PARTY_ID
    AND i.TOPIC = 'CANCELLATION_REQUEST'
    AND i.INTERACTION_DATE >= DATEADD('day', -14, CURRENT_TIMESTAMP())
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL')

UNION ALL

-- S07: Minor party → blocks all marketing/sales
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S07', 'Minor party',
    'Customer is under 18 — cannot market insurance products',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE c.AGE < 18
  AND a.CATEGORY IN ('CROSS_SELL', 'RETENTION')

UNION ALL

-- S08: Duplicate action cooldown (30 days) → blocks same action type
SELECT
    al.PARTY_ID, al.ACTION_TYPE,
    'S08', 'Duplicate action cooldown',
    'Same action executed within last 30 days — one touch per month',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ,
    DATEADD('day', 30, al.EXECUTED_AT)::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.ACTION_LOG al
WHERE al.EXECUTED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())

UNION ALL

-- S09: Negative-sentiment active conversation → blocks CROSS_SELL
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S09', 'Negative-sentiment active conversation',
    'Customer has unresolved negative interaction in last 7 days — resolve first',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_INTERACTION i ON c.PARTY_ID = i.PARTY_ID
    AND i.SENTIMENT = 'NEGATIVE'
    AND i.RESOLUTION IN ('ESCALATED', 'UNRESOLVED')
    AND i.INTERACTION_DATE >= DATEADD('day', -7, CURRENT_TIMESTAMP())
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL')

UNION ALL

-- S10: Premium-shock grace period → blocks CROSS_SELL
SELECT DISTINCT
    c.PARTY_ID, a.ACTION_TYPE,
    'S10', 'Premium-shock grace period',
    'Customer absorbed >15% premium increase recently — let rate settle before upselling',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.SERVING.CUSTOMER_360 c
JOIN MERIDIAN.CURATED.DT_POLICY p ON c.PARTY_ID = p.PARTY_ID
    AND p.RATE_SHOCK_FLAG = TRUE
    AND p.STATUS = 'PENDING_RENEWAL'
    AND p.DAYS_TO_RENEWAL BETWEEN -30 AND 45
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.CATEGORY IN ('CROSS_SELL')

UNION ALL

-- S11: Excessive contact frequency → blocks all non-urgent
SELECT DISTINCT
    i.PARTY_ID, a.ACTION_TYPE,
    'S11', 'Excessive contact frequency',
    'Customer contacted 3+ times in last 14 days — over-contact risk',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM (
    SELECT PARTY_ID, COUNT(*) AS cnt
    FROM MERIDIAN.CURATED.DT_INTERACTION
    WHERE DIRECTION = 'OUTBOUND'
      AND INTERACTION_DATE >= DATEADD('day', -14, CURRENT_TIMESTAMP())
    GROUP BY PARTY_ID
    HAVING cnt >= 3
) i
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE a.ACTION_TYPE NOT IN ('STALLED_CLAIM_ESCALATION')

UNION ALL

-- S12: Do-not-contact flag → blocks ALL outbound
SELECT DISTINCT
    i.PARTY_ID, a.ACTION_TYPE,
    'S12', 'Do-not-contact flag',
    'Customer has opted out of contact — legally required to respect',
    CURRENT_TIMESTAMP()::TIMESTAMP_NTZ, NULL::TIMESTAMP_NTZ
FROM MERIDIAN.CURATED.DT_INTERACTION i
CROSS JOIN MERIDIAN.SERVING.ACTION_CATALOG a
WHERE i.TOPIC = 'DO_NOT_CONTACT';


-- ====================================================================
-- 3. NBA_RECOMMENDATION — candidate generation + ranking
--    One row per (PARTY_ID, ACTION_TYPE). Eligibility predicates
--    determine candidates; scoring ranks them.
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE SERVING.NBA_RECOMMENDATION
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
WITH
-- ── Candidate generation: per-action eligibility predicates ────────
candidates AS (

    -- RETENTION_LOYALTY_CREDIT: high churn risk, has premium
    SELECT c.PARTY_ID, 'RETENTION_LOYALTY_CREDIT' AS ACTION_TYPE,
           c.CHURN_RISK_SCORE AS PROPENSITY,
           c.TOTAL_PREMIUM    AS PREMIUM_AT_RISK,
           c.NEAREST_RENEWAL_DAYS,
           c.MAX_CLAIM_DAYS_OPEN,
           c.CHURN_REASON_CODES AS REASON_CODES,
           'Churn risk score ' || ROUND(c.CHURN_RISK_SCORE, 2) || ' with ' ||
             ARRAY_SIZE(c.CHURN_REASON_CODES) || ' active signals' AS REASON_TEXT,
           NULL AS EVIDENCE_REF
    FROM SERVING.CUSTOMER_360 c
    WHERE c.CHURN_RISK_SCORE > 0.15
      AND c.TOTAL_PREMIUM > 0
      AND c.NEAREST_RENEWAL_DAYS BETWEEN 0 AND 90

    UNION ALL

    -- SUPERVISOR_RATE_REVIEW: rate shock on pending renewal
    SELECT c.PARTY_ID, 'SUPERVISOR_RATE_REVIEW',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, c.MAX_CLAIM_DAYS_OPEN,
           c.CHURN_REASON_CODES,
           'Pending renewal with rate shock — premium increase exceeds 15% threshold, requires supervisor review',
           p.POLICY_ID
    FROM SERVING.CUSTOMER_360 c
    JOIN CURATED.DT_POLICY p ON c.PARTY_ID = p.PARTY_ID
        AND p.STATUS = 'PENDING_RENEWAL'
        AND p.RATE_SHOCK_FLAG = TRUE

    UNION ALL

    -- STALLED_CLAIM_ESCALATION: open claim > 30 days
    SELECT c.PARTY_ID, 'STALLED_CLAIM_ESCALATION',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, cl.DAYS_OPEN,
           c.CHURN_REASON_CODES,
           cl.CLAIM_TYPE || ' claim ' || cl.CLAIM_ID || ' open ' || cl.DAYS_OPEN ||
             ' days — exceeds 30-day SLA, escalate to claims manager',
           cl.CLAIM_ID
    FROM SERVING.CUSTOMER_360 c
    JOIN CURATED.DT_CLAIM cl ON c.PARTY_ID = cl.PARTY_ID
        AND cl.UNRESOLVED_FLAG = TRUE

    UNION ALL

    -- HONOUR_CALLBACK: customer was promised callback (AI-detected)
    SELECT c.PARTY_ID, 'HONOUR_CALLBACK',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, c.MAX_CLAIM_DAYS_OPEN,
           c.CHURN_REASON_CODES,
           'Customer was promised a callback that was not fulfilled',
           ai.INTERACTION_ID
    FROM SERVING.CUSTOMER_360 c
    JOIN ENRICHED.INTERACTION_AI ai ON c.PARTY_ID = ai.PARTY_ID
        AND ai.AI_PROMISED_CALLBACK = TRUE

    UNION ALL

    -- HOME_BUNDLE_CROSS_SELL: household has auto but no home
    SELECT c.PARTY_ID, 'HOME_BUNDLE_CROSS_SELL',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, c.MAX_CLAIM_DAYS_OPEN,
           ARRAY_CAT(
               ARRAY_CONSTRUCT('BUNDLE_GAP_HOME', 'MULTI_POLICY_DISCOUNT'),
               COALESCE(c.CHURN_REASON_CODES, ARRAY_CONSTRUCT())
           ),
           'Household has auto but no home policy — bundling reduces churn risk by ~50% and increases LTV',
           c.HOUSEHOLD_ID
    FROM SERVING.CUSTOMER_360 c
    JOIN SERVING.DT_HOUSEHOLD_BUNDLE_GAP bg ON c.HOUSEHOLD_ID = bg.HOUSEHOLD_ID
        AND bg.GAP_NEEDS_HOME = TRUE

    UNION ALL

    -- BILLING_MANDATE_REPAIR: payment distress
    SELECT c.PARTY_ID, 'BILLING_MANDATE_REPAIR',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, c.MAX_CLAIM_DAYS_OPEN,
           c.CHURN_REASON_CODES,
           'Customer has ' || c.DISTRESSED_BILLS || ' past-due or collections billing records — mandate repair prevents lapse',
           NULL
    FROM SERVING.CUSTOMER_360 c
    WHERE c.DISTRESSED_BILLS > 0

    UNION ALL

    -- PROACTIVE_WINBACK: competitor quote or churn language
    SELECT c.PARTY_ID, 'PROACTIVE_WINBACK',
           c.CHURN_RISK_SCORE, c.TOTAL_PREMIUM,
           c.NEAREST_RENEWAL_DAYS, c.MAX_CLAIM_DAYS_OPEN,
           c.CHURN_REASON_CODES,
           CASE
             WHEN c.SIG_COMPETITOR_MENTION > 0 THEN 'Customer mentioned competitor in recent call — proactive retention outreach needed'
             WHEN c.SIG_CHURN_LANGUAGE > 0     THEN 'Customer used explicit churn language in recent call — proactive retention outreach needed'
             ELSE 'Customer showing competitive shopping behaviour'
           END,
           NULL
    FROM SERVING.CUSTOMER_360 c
    WHERE c.SIG_COMPETITOR_MENTION > 0 OR c.SIG_CHURN_LANGUAGE > 0
),

-- ── Scoring: propensity × normalised_value × urgency ──────────────
scored AS (
    SELECT
        cand.*,
        cat.ACTION_NAME,
        cat.CATEGORY,
        cat.CHANNEL,
        cat.EV_SHARE_OF_PREMIUM,
        cat.COST_TO_SERVE,
        cat.NEEDS_SUPERVISOR,
        cat.SUPERVISOR_THRESHOLD,
        cat.SLA_DAYS,

        -- Normalised expected value
        ROUND(cand.PROPENSITY * cat.EV_SHARE_OF_PREMIUM * cand.PREMIUM_AT_RISK, 2)
            AS EXPECTED_VALUE,

        -- Urgency factor: rises with renewal proximity and claim ageing
        GREATEST(0.3,
            CASE
              WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 14 THEN 1.0
              WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 30 THEN 0.8
              WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 45 THEN 0.6
              ELSE 0.3
            END
          + CASE
              WHEN cand.MAX_CLAIM_DAYS_OPEN IS NOT NULL AND cand.MAX_CLAIM_DAYS_OPEN > 60 THEN 0.3
              WHEN cand.MAX_CLAIM_DAYS_OPEN IS NOT NULL AND cand.MAX_CLAIM_DAYS_OPEN > 30 THEN 0.15
              ELSE 0.0
            END
        ) AS URGENCY,

        -- Composite NBA score
        ROUND(
            cand.PROPENSITY
          * cat.EV_SHARE_OF_PREMIUM
          * cand.PREMIUM_AT_RISK
          * GREATEST(0.3,
              CASE
                WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 14 THEN 1.0
                WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 30 THEN 0.8
                WHEN cand.NEAREST_RENEWAL_DAYS IS NOT NULL AND cand.NEAREST_RENEWAL_DAYS <= 45 THEN 0.6
                ELSE 0.3
              END
            + CASE
                WHEN cand.MAX_CLAIM_DAYS_OPEN IS NOT NULL AND cand.MAX_CLAIM_DAYS_OPEN > 60 THEN 0.3
                WHEN cand.MAX_CLAIM_DAYS_OPEN IS NOT NULL AND cand.MAX_CLAIM_DAYS_OPEN > 30 THEN 0.15
                ELSE 0.0
              END
          ),
        2) AS NBA_SCORE,

        -- Suppression status
        s.RULE_ID  AS SUPPRESSION_RULE_ID,
        s.RULE_NAME AS SUPPRESSION_RULE_NAME,
        s.REASON   AS SUPPRESSION_REASON,
        CASE WHEN s.RULE_ID IS NOT NULL THEN 'SUPPRESSED' ELSE 'RECOMMENDED' END AS STATUS,

        -- Rank within customer (recommended first, then by NBA_SCORE)
        ROW_NUMBER() OVER (
            PARTITION BY cand.PARTY_ID
            ORDER BY
                CASE WHEN s.RULE_ID IS NOT NULL THEN 1 ELSE 0 END,
                cand.PROPENSITY * cat.EV_SHARE_OF_PREMIUM * cand.PREMIUM_AT_RISK DESC
        ) AS RANK_FOR_CUSTOMER
    FROM candidates cand
    JOIN SERVING.ACTION_CATALOG cat ON cand.ACTION_TYPE = cat.ACTION_TYPE
    LEFT JOIN SERVING.DT_SUPPRESSION s
        ON  cand.PARTY_ID    = s.PARTY_ID
        AND cand.ACTION_TYPE = s.ACTION_TYPE
)

SELECT
    PARTY_ID, ACTION_TYPE, ACTION_NAME, CATEGORY, CHANNEL, STATUS,
    ROUND(PROPENSITY, 4)      AS PROPENSITY,
    PREMIUM_AT_RISK,
    EXPECTED_VALUE,
    URGENCY,
    NBA_SCORE,
    NEAREST_RENEWAL_DAYS,
    NEEDS_SUPERVISOR,
    SUPERVISOR_THRESHOLD,
    SLA_DAYS,
    REASON_TEXT,
    REASON_CODES,
    EVIDENCE_REF,
    SUPPRESSION_RULE_ID,
    SUPPRESSION_RULE_NAME,
    SUPPRESSION_REASON,
    RANK_FOR_CUSTOMER
FROM scored;


-- ====================================================================
-- 4. ACTION_LOG — append-only audit trail (never replaced)
-- ====================================================================
CREATE TABLE IF NOT EXISTS SERVING.ACTION_LOG (
    LOG_ID             VARCHAR        NOT NULL DEFAULT UUID_STRING(),
    RECOMMENDATION_ID  VARCHAR,
    PARTY_ID           VARCHAR        NOT NULL,
    ACTION_TYPE        VARCHAR        NOT NULL,
    EXECUTED_AT        TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    EXECUTED_BY        VARCHAR,
    CHANNEL            VARCHAR,
    OUTCOME            VARCHAR,
    NOTES              VARCHAR,
    CONSTRAINT PK_ACTION_LOG PRIMARY KEY (LOG_ID)
);


-- ====================================================================
-- 5. V_SUPPRESSION_AUDIT — guardrail dashboard
--    Per rule: how many actions blocked, customers affected,
--    total expected value deliberately forgone.
-- ====================================================================
CREATE OR REPLACE VIEW SERVING.V_SUPPRESSION_AUDIT AS
SELECT
    r.SUPPRESSION_RULE_ID,
    r.SUPPRESSION_RULE_NAME,
    COUNT(*)                         AS ACTIONS_BLOCKED,
    COUNT(DISTINCT r.PARTY_ID)       AS CUSTOMERS_AFFECTED,
    SUM(r.EXPECTED_VALUE)            AS EXPECTED_VALUE_FORGONE,
    ROUND(AVG(r.PROPENSITY), 4)      AS AVG_CHURN_RISK_BLOCKED
FROM SERVING.NBA_RECOMMENDATION r
WHERE r.STATUS = 'SUPPRESSED'
GROUP BY r.SUPPRESSION_RULE_ID, r.SUPPRESSION_RULE_NAME
ORDER BY EXPECTED_VALUE_FORGONE DESC;
