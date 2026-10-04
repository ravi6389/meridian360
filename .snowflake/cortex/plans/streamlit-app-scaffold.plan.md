# Plan: Streamlit-in-Snowflake App

## Architecture

**Single file `streamlit/app.py`** — Streamlit-in-Snowflake apps run inside Snowflake, so we use `snowflake.snowpark.context.get_active_session()` for data access. No external connections.

**`streamlit/environment.yml`** — declares `plotly` for the sentiment trajectory chart.

## Data Contracts

| Tab | Source Object | Key Columns |
|-----|--------------|-------------|
| Worklist | `SERVING.V_RETENTION_WORKLIST` | PARTY_ID, FIRST_NAME, LAST_NAME, NEAREST_RENEWAL_DAYS, CHURN_RISK_SCORE, TOTAL_PREMIUM, EXPECTED_LOSS, NUM_SIGNALS, PRIMARY_CROSS_SELL_LOB, RANK_EXPECTED_LOSS, RANK_CHURN_RISK |
| 360 Profile | `SERVING.CUSTOMER_360` | All 41 columns — profile header, signal terms, reason codes |
| 360 Sentiment | `ENRICHED.INTERACTION_AI` | PARTY_ID, INTERACTION_ID, AI_SENTIMENT_SCORE, AI_SUMMARY, AI_KEY_QUOTE, AI_COMPETITOR_MENTIONED, PROCESSED_AT (joined with DT_INTERACTION for INTERACTION_DATE) |
| 360 Timeline | `SERVING.CUSTOMER_TIMELINE` | PARTY_ID, EVENT_TS, EVENT_TYPE, CATEGORY, DESCRIPTION |
| 360 NBA | `SERVING.NBA_RECOMMENDATION` | PARTY_ID, ACTION_TYPE, ACTION_NAME, STATUS, NEEDS_SUPERVISOR, EXPECTED_VALUE, REASON_TEXT, EVIDENCE_REF, SUPPRESSION_RULE_NAME, SUPPRESSION_REASON, RANK_FOR_CUSTOMER |
| 360 Action | `SERVING.ACTION_LOG` | INSERT via session.sql() |
| Governance | `SERVING.V_SUPPRESSION_AUDIT` | All columns |
| Governance | `ENRICHED.INTERACTION_AI` | Aggregate stats |

## Visual Design

- **Colour semantics only**: red (#D32F2F) = high risk / suppressed, amber (#F57C00) = needs approval, green (#388E3C) = resolved / low risk, grey (#9E9E9E) = suppressed text
- **No decorative colour** — white/dark backgrounds, black text, subtle borders
- **Churn score** rendered as a coloured progress bar (green < 0.3, amber 0.3-0.5, red > 0.5)
- **NBA cards** in `st.container` with left border colour: blue for recommended, grey for suppressed
- **Supervisor badge**: amber pill with lock icon
- **Warning badges** in profile header: red pills for open claim, competitor shopping, cancellation request

## Tab 1: Worklist

1. `st.toggle` for sort order (Expected Loss vs Churn Risk)
2. `st.dataframe` with formatted columns, conditional formatting via CSS
3. Each row has a "View" button that sets `st.session_state.selected_customer` and switches to Tab 2

## Tab 2: Customer 360

1. **Profile header**: 3-column layout — name/ID, metrics (tenure, premium, churn score with bar), warning badges
2. **Sentiment trajectory**: Plotly line chart from INTERACTION_AI joined with DT_INTERACTION for dates, showing score declining across calls
3. **Timeline**: `st.container` per event, newest first, with category icon/colour, timestamp, description. AI-enriched interactions show summary + key quote
4. **NBA Panel**: Two sections:
   - **Recommended**: cards ranked by expected value, each with reason text, propensity, EV, evidence ref, approval badge, and an "Execute" button that INSERTs to ACTION_LOG
   - **Suppressed**: greyed-out cards showing each blocking rule and rationale

## Tab 3: Governance

1. **Suppression audit table** from V_SUPPRESSION_AUDIT
2. **Enrichment QA metrics**: parse success rate, intent distribution bar chart, churn signal count, competitor mention count
3. **Rule book**: expandable section listing all 12 suppression rules with descriptions

## Deployment

```sql
CREATE STAGE IF NOT EXISTS MERIDIAN.APP.STREAMLIT_STAGE;
PUT 'file://streamlit/app.py' @MERIDIAN.APP.STREAMLIT_STAGE/meridian360 OVERWRITE=TRUE;
PUT 'file://streamlit/environment.yml' @MERIDIAN.APP.STREAMLIT_STAGE/meridian360 OVERWRITE=TRUE;
CREATE OR REPLACE STREAMLIT MERIDIAN.APP.MERIDIAN_360
  ROOT_LOCATION = '@MERIDIAN.APP.STREAMLIT_STAGE/meridian360'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = MERIDIAN_WH;
```
