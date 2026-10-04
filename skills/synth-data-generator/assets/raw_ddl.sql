/*=====================================================================
  Meridian 360 — 02_raw_ddl.sql
  RAW landing tables for all entities defined in docs/ontology.md.
  Idempotent — CREATE IF NOT EXISTS so re-running is safe.
  Data is frozen after seed load; these tables must never be replaced.
=====================================================================*/

USE ROLE MERIDIAN_BUILDER;
USE WAREHOUSE MERIDIAN_WH;
USE DATABASE MERIDIAN;
USE SCHEMA RAW;

-- ====================================================================
-- HOUSEHOLD
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.HOUSEHOLD (
  HOUSEHOLD_ID   VARCHAR        NOT NULL,
  ADDRESS        VARCHAR,
  STATE          VARCHAR(2),
  POSTAL_CODE    VARCHAR(10),
  MEMBER_COUNT   NUMBER,
  CONSTRAINT PK_HOUSEHOLD PRIMARY KEY (HOUSEHOLD_ID)
);

-- ====================================================================
-- PARTY
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.PARTY (
  PARTY_ID       VARCHAR        NOT NULL,
  FIRST_NAME     VARCHAR,
  LAST_NAME      VARCHAR,
  DATE_OF_BIRTH  DATE,
  EMAIL          VARCHAR,
  PHONE          VARCHAR,
  MAILING_ADDRESS VARCHAR,
  STATE          VARCHAR(2),
  POSTAL_CODE    VARCHAR(10),
  CREATED_AT     TIMESTAMP_NTZ,
  HOUSEHOLD_ID   VARCHAR,
  CONSTRAINT PK_PARTY PRIMARY KEY (PARTY_ID)
);

-- ====================================================================
-- POLICY
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.POLICY (
  POLICY_ID        VARCHAR        NOT NULL,
  PARTY_ID         VARCHAR        NOT NULL,
  LINE_OF_BUSINESS VARCHAR,
  STATUS           VARCHAR,
  EFFECTIVE_DATE   DATE,
  EXPIRATION_DATE  DATE,
  PREMIUM_AMOUNT   NUMBER(12,2),
  DEDUCTIBLE       NUMBER(12,2),
  COVERAGE_LIMIT   NUMBER(12,2),
  BIND_DATE        DATE,
  CANCELLATION_DATE DATE,
  RENEWAL_COUNT    NUMBER,
  CONSTRAINT PK_POLICY PRIMARY KEY (POLICY_ID)
);

-- ====================================================================
-- CLAIM
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.CLAIM (
  CLAIM_ID        VARCHAR        NOT NULL,
  POLICY_ID       VARCHAR        NOT NULL,
  PARTY_ID        VARCHAR        NOT NULL,
  LOSS_DATE       DATE,
  REPORT_DATE     DATE,
  CLAIM_STATUS    VARCHAR,
  CLAIM_TYPE      VARCHAR,
  RESERVE_AMOUNT  NUMBER(12,2),
  PAID_AMOUNT     NUMBER(12,2),
  FAULT_INDICATOR VARCHAR,
  CONSTRAINT PK_CLAIM PRIMARY KEY (CLAIM_ID)
);

-- ====================================================================
-- BILLING
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.BILLING (
  BILLING_ID      VARCHAR        NOT NULL,
  POLICY_ID       VARCHAR        NOT NULL,
  PARTY_ID        VARCHAR        NOT NULL,
  DUE_DATE        DATE,
  AMOUNT_DUE      NUMBER(12,2),
  AMOUNT_PAID     NUMBER(12,2),
  PAYMENT_DATE    DATE,
  PAYMENT_METHOD  VARCHAR,
  BILLING_STATUS  VARCHAR,
  CONSTRAINT PK_BILLING PRIMARY KEY (BILLING_ID)
);

-- ====================================================================
-- INTERACTION
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.INTERACTION (
  INTERACTION_ID    VARCHAR          NOT NULL,
  PARTY_ID          VARCHAR          NOT NULL,
  CHANNEL           VARCHAR,
  DIRECTION         VARCHAR,
  INTERACTION_DATE  TIMESTAMP_NTZ,
  DURATION_SECONDS  NUMBER,
  TOPIC             VARCHAR,
  TRANSCRIPT_TEXT   VARCHAR(16777216),
  SUMMARY           VARCHAR,
  SENTIMENT         VARCHAR,
  SENTIMENT_SCORE   NUMBER(5,4),
  RESOLUTION        VARCHAR,
  RELATED_POLICY_ID VARCHAR,
  RELATED_CLAIM_ID  VARCHAR,
  CONSTRAINT PK_INTERACTION PRIMARY KEY (INTERACTION_ID)
);

-- ====================================================================
-- QUOTE
-- ====================================================================
CREATE TABLE IF NOT EXISTS RAW.QUOTE (
  QUOTE_ID         VARCHAR        NOT NULL,
  PARTY_ID         VARCHAR,
  LINE_OF_BUSINESS VARCHAR,
  QUOTED_PREMIUM   NUMBER(12,2),
  QUOTE_DATE       DATE,
  QUOTE_STATUS     VARCHAR,
  SOURCE           VARCHAR,
  CONSTRAINT PK_QUOTE PRIMARY KEY (QUOTE_ID)
);

-- ====================================================================
-- Bulk-load procedure: loads all CSVs from SEED_STAGE into RAW tables
-- ====================================================================
CREATE OR REPLACE PROCEDURE RAW.SP_LOAD_SEED_DATA()
  RETURNS VARCHAR
  LANGUAGE SQL
  EXECUTE AS CALLER
AS
-- Loads all seed CSVs from RAW.SEED_STAGE into RAW tables. Idempotent via TRUNCATE + COPY.
BEGIN
  -- Truncate and reload each table from its matching CSV.
  -- Order: Household first (referenced by Party), then Party, then dependents.

  TRUNCATE TABLE IF EXISTS RAW.HOUSEHOLD;
  COPY INTO RAW.HOUSEHOLD
    FROM @RAW.SEED_STAGE/household.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.PARTY;
  COPY INTO RAW.PARTY
    FROM @RAW.SEED_STAGE/party.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.POLICY;
  COPY INTO RAW.POLICY
    FROM @RAW.SEED_STAGE/policy.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.CLAIM;
  COPY INTO RAW.CLAIM
    FROM @RAW.SEED_STAGE/claim.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.BILLING;
  COPY INTO RAW.BILLING
    FROM @RAW.SEED_STAGE/billing.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.INTERACTION;
  COPY INTO RAW.INTERACTION
    FROM @RAW.SEED_STAGE/interaction.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  TRUNCATE TABLE IF EXISTS RAW.QUOTE;
  COPY INTO RAW.QUOTE
    FROM @RAW.SEED_STAGE/quote.csv
    FILE_FORMAT = RAW.CSV_FORMAT
    ON_ERROR = 'CONTINUE';

  RETURN 'Seed data loaded successfully into all RAW tables';
END;
