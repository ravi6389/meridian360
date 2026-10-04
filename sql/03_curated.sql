/*=====================================================================
  Meridian 360 — 03_curated.sql
  Curated-layer dynamic tables: cleansed, conformed, derived flags.
  Each table adds computed columns on top of RAW; no cross-entity joins
  except Customer which rolls up the Household.
  TARGET_LAG = 20 minutes (demo cadence per AGENTS.md).
  Idempotent — CREATE OR REPLACE.
=====================================================================*/

USE ROLE MERIDIAN_BUILDER;
USE WAREHOUSE MERIDIAN_WH;
USE DATABASE MERIDIAN;

-- ====================================================================
-- DT_CUSTOMER — Party + Household rollup, tenure, age
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_CUSTOMER
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    p.PARTY_ID,
    p.FIRST_NAME,
    p.LAST_NAME,
    p.DATE_OF_BIRTH,
    p.EMAIL,
    p.PHONE,
    p.MAILING_ADDRESS,
    p.STATE,
    p.POSTAL_CODE,
    p.CREATED_AT,
    p.HOUSEHOLD_ID,
    h.ADDRESS          AS HOUSEHOLD_ADDRESS,
    h.STATE            AS HOUSEHOLD_STATE,
    h.POSTAL_CODE      AS HOUSEHOLD_POSTAL_CODE,
    h.MEMBER_COUNT     AS HOUSEHOLD_MEMBER_COUNT,
    ROUND(DATEDIFF('day', p.CREATED_AT, CURRENT_TIMESTAMP()) / 365.25, 1)
                       AS TENURE_YEARS,
    DATEDIFF('year', p.DATE_OF_BIRTH, CURRENT_DATE())
                       AS AGE
FROM RAW.PARTY p
JOIN RAW.HOUSEHOLD h ON p.HOUSEHOLD_ID = h.HOUSEHOLD_ID;

-- ====================================================================
-- DT_POLICY — days to renewal, rate-shock flag
-- Rate shock = PENDING_RENEWAL and a competitor quote exists for the
-- same party+LOB that is >15% cheaper than the current premium.
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_POLICY
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    pol.POLICY_ID,
    pol.PARTY_ID,
    pol.LINE_OF_BUSINESS,
    pol.STATUS,
    pol.EFFECTIVE_DATE,
    pol.EXPIRATION_DATE,
    pol.PREMIUM_AMOUNT,
    pol.DEDUCTIBLE,
    pol.COVERAGE_LIMIT,
    pol.BIND_DATE,
    pol.CANCELLATION_DATE,
    pol.RENEWAL_COUNT,
    DATEDIFF('day', CURRENT_DATE(), pol.EXPIRATION_DATE)  AS DAYS_TO_RENEWAL,
    CASE
      WHEN pol.STATUS = 'PENDING_RENEWAL'
       AND cq.MIN_QUOTED < pol.PREMIUM_AMOUNT * 0.85
      THEN TRUE
      ELSE FALSE
    END AS RATE_SHOCK_FLAG
FROM RAW.POLICY pol
LEFT JOIN (
    SELECT PARTY_ID, LINE_OF_BUSINESS,
           MIN(QUOTED_PREMIUM) AS MIN_QUOTED
    FROM RAW.QUOTE
    WHERE PARTY_ID IS NOT NULL
    GROUP BY PARTY_ID, LINE_OF_BUSINESS
) cq
  ON  pol.PARTY_ID         = cq.PARTY_ID
  AND pol.LINE_OF_BUSINESS = cq.LINE_OF_BUSINESS;

-- ====================================================================
-- DT_CLAIM — ageing (days open), unresolved flag
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_CLAIM
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    c.CLAIM_ID,
    c.POLICY_ID,
    c.PARTY_ID,
    c.LOSS_DATE,
    c.REPORT_DATE,
    c.CLAIM_STATUS,
    c.CLAIM_TYPE,
    c.RESERVE_AMOUNT,
    c.PAID_AMOUNT,
    c.FAULT_INDICATOR,
    CASE WHEN c.CLAIM_STATUS IN ('OPEN', 'REOPENED')
         THEN DATEDIFF('day', c.REPORT_DATE, CURRENT_DATE())
         ELSE NULL
    END AS DAYS_OPEN,
    CASE WHEN c.CLAIM_STATUS IN ('OPEN', 'REOPENED')
          AND DATEDIFF('day', c.REPORT_DATE, CURRENT_DATE()) > 30
         THEN TRUE ELSE FALSE
    END AS UNRESOLVED_FLAG
FROM RAW.CLAIM c;

-- ====================================================================
-- DT_BILLING — payment-distress flag, days past due
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_BILLING
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    b.BILLING_ID,
    b.POLICY_ID,
    b.PARTY_ID,
    b.DUE_DATE,
    b.AMOUNT_DUE,
    b.AMOUNT_PAID,
    b.PAYMENT_DATE,
    b.PAYMENT_METHOD,
    b.BILLING_STATUS,
    CASE WHEN b.BILLING_STATUS IN ('PAST_DUE', 'COLLECTIONS')
         THEN DATEDIFF('day', b.DUE_DATE, CURRENT_DATE())
         ELSE 0
    END AS DAYS_PAST_DUE,
    b.BILLING_STATUS IN ('PAST_DUE', 'COLLECTIONS') AS PAYMENT_DISTRESS_FLAG
FROM RAW.BILLING b;

-- ====================================================================
-- DT_WEB_SESSION — web-channel interactions, risk-page flag
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_WEB_SESSION
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    i.INTERACTION_ID,
    i.PARTY_ID,
    i.INTERACTION_DATE,
    i.DURATION_SECONDS,
    i.TOPIC,
    i.SUMMARY,
    i.TOPIC IN ('CANCELLATION_PAGE', 'RATE_COMPARISON') AS RISK_PAGE_FLAG
FROM RAW.INTERACTION i
WHERE i.CHANNEL = 'WEB';

-- ====================================================================
-- DT_QUOTE — curated quotes
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_QUOTE
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    q.QUOTE_ID,
    q.PARTY_ID,
    q.LINE_OF_BUSINESS,
    q.QUOTED_PREMIUM,
    q.QUOTE_DATE,
    q.QUOTE_STATUS,
    q.SOURCE
FROM RAW.QUOTE q;

-- ====================================================================
-- DT_INTERACTION — all channels, transcript text carried through
-- ====================================================================
CREATE OR REPLACE DYNAMIC TABLE CURATED.DT_INTERACTION
  TARGET_LAG = '20 minutes'
  WAREHOUSE  = MERIDIAN_WH
AS
SELECT
    i.INTERACTION_ID,
    i.PARTY_ID,
    i.CHANNEL,
    i.DIRECTION,
    i.INTERACTION_DATE,
    i.DURATION_SECONDS,
    i.TOPIC,
    i.TRANSCRIPT_TEXT,
    i.SUMMARY,
    i.SENTIMENT,
    i.SENTIMENT_SCORE,
    i.RESOLUTION,
    i.RELATED_POLICY_ID,
    i.RELATED_CLAIM_ID
FROM RAW.INTERACTION i;
