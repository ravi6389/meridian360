/*=====================================================================
  Meridian 360 — 01_setup.sql
  Infrastructure: database, schemas, warehouse, stage, file format.
  Idempotent — safe to re-run.
=====================================================================*/

-- --------------------------------------------------------------------
-- Role context
-- --------------------------------------------------------------------
USE ROLE SYSADMIN;

-- --------------------------------------------------------------------
-- Warehouse
-- --------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS MERIDIAN_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT        = 'Meridian 360 — Customer 360 & NBA engine';

USE WAREHOUSE MERIDIAN_WH;

-- --------------------------------------------------------------------
-- Database
-- --------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS MERIDIAN
  COMMENT = 'Meridian 360 — Customer 360 & NBA engine for composite P&C insurer';

-- --------------------------------------------------------------------
-- Schemas
-- --------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS MERIDIAN.RAW
  COMMENT = 'Immutable landing zone for source-system extracts and synthetic seed data';

CREATE SCHEMA IF NOT EXISTS MERIDIAN.CURATED
  COMMENT = 'Cleansed, typed, deduplicated, conformed views — no cross-entity joins';

CREATE SCHEMA IF NOT EXISTS MERIDIAN.ENRICHED
  COMMENT = 'Cross-entity joins, AI-derived columns, feature engineering (dynamic tables)';

CREATE SCHEMA IF NOT EXISTS MERIDIAN.SERVING
  COMMENT = 'Business-ready aggregates, NBA recommendations, suppression, action log';

CREATE SCHEMA IF NOT EXISTS MERIDIAN.INTELLIGENCE
  COMMENT = 'Cortex Search service, Cortex Analyst semantic model';

CREATE SCHEMA IF NOT EXISTS MERIDIAN.APP
  COMMENT = 'Streamlit app, stored procedures, UDFs';

-- --------------------------------------------------------------------
-- Grant ownership to a builder role (create if needed)
-- --------------------------------------------------------------------
USE ROLE SECURITYADMIN;

CREATE ROLE IF NOT EXISTS MERIDIAN_BUILDER
  COMMENT = 'Builder role for the Meridian 360 project';

-- Grant warehouse usage
GRANT USAGE   ON WAREHOUSE MERIDIAN_WH       TO ROLE MERIDIAN_BUILDER;
GRANT OPERATE ON WAREHOUSE MERIDIAN_WH       TO ROLE MERIDIAN_BUILDER;

-- Grant database-level privileges
GRANT USAGE                ON DATABASE MERIDIAN TO ROLE MERIDIAN_BUILDER;
GRANT CREATE SCHEMA        ON DATABASE MERIDIAN TO ROLE MERIDIAN_BUILDER;

-- Grant schema-level privileges for each schema
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.RAW          TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.CURATED      TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.ENRICHED     TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.SERVING      TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.INTELLIGENCE TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON SCHEMA MERIDIAN.APP          TO ROLE MERIDIAN_BUILDER;

-- Future grants so new objects are automatically accessible
GRANT ALL PRIVILEGES ON FUTURE TABLES         IN SCHEMA MERIDIAN.RAW      TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON FUTURE VIEWS          IN SCHEMA MERIDIAN.CURATED  TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON FUTURE DYNAMIC TABLES IN SCHEMA MERIDIAN.ENRICHED TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON FUTURE DYNAMIC TABLES IN SCHEMA MERIDIAN.SERVING  TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON FUTURE VIEWS          IN SCHEMA MERIDIAN.SERVING  TO ROLE MERIDIAN_BUILDER;
GRANT ALL PRIVILEGES ON FUTURE TABLES         IN SCHEMA MERIDIAN.SERVING  TO ROLE MERIDIAN_BUILDER;

-- Grant role to current user
GRANT ROLE MERIDIAN_BUILDER TO USER RAVI6389;

-- --------------------------------------------------------------------
-- Switch to builder role for remaining setup
-- --------------------------------------------------------------------
USE ROLE MERIDIAN_BUILDER;
USE DATABASE MERIDIAN;
USE SCHEMA RAW;

-- --------------------------------------------------------------------
-- Internal stage for CSV seed files
-- --------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS MERIDIAN.RAW.SEED_STAGE
  COMMENT = 'Internal stage for synthetic seed CSV files';

-- --------------------------------------------------------------------
-- CSV file format
-- --------------------------------------------------------------------
CREATE FILE FORMAT IF NOT EXISTS MERIDIAN.RAW.CSV_FORMAT
  TYPE                 = 'CSV'
  FIELD_DELIMITER      = ','
  SKIP_HEADER          = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF              = ('NULL', 'null', '')
  EMPTY_FIELD_AS_NULL  = TRUE
  TRIM_SPACE           = TRUE
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
  COMMENT              = 'Standard CSV format for seed data loading';
