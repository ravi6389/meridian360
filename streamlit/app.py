import streamlit as st
import plotly.graph_objects as go
import json
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Meridian 360", layout="wide")

session = get_active_session()

# ─── Design tokens ──────────────────────────────────────────────────
RED    = "#D32F2F"
AMBER  = "#F57C00"
GREEN  = "#388E3C"
GREY   = "#9E9E9E"
BLUE   = "#1565C0"
BG_LIGHT = "#FAFAFA"

st.markdown("""
<style>
/* Global */
section[data-testid="stSidebar"] { display: none; }
.block-container { padding-top: 1rem; max-width: 1200px; }

/* Metric cards */
.metric-row { display: flex; gap: 1.2rem; margin-bottom: 1rem; }
.metric-card {
    background: #FAFAFA; border: 1px solid #E0E0E0; border-radius: 8px;
    padding: 0.8rem 1.2rem; flex: 1; text-align: center;
}
.metric-card .label { font-size: 0.75rem; color: #757575; text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card .value { font-size: 1.5rem; font-weight: 600; margin-top: 0.2rem; }

/* Badges */
.badge {
    display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px;
    font-size: 0.72rem; font-weight: 600; margin-right: 0.3rem; margin-bottom: 0.3rem;
}
.badge-red    { background: #FFEBEE; color: #D32F2F; }
.badge-amber  { background: #FFF3E0; color: #F57C00; }
.badge-green  { background: #E8F5E9; color: #388E3C; }
.badge-grey   { background: #F5F5F5; color: #757575; }
.badge-blue   { background: #E3F2FD; color: #1565C0; }

/* Churn bar */
.churn-bar-bg {
    background: #E0E0E0; border-radius: 4px; height: 10px; width: 100%;
    margin-top: 0.3rem;
}
.churn-bar-fill { border-radius: 4px; height: 10px; }

/* NBA cards */
.nba-card {
    border-left: 4px solid #1565C0; background: #FAFAFA;
    border-radius: 0 8px 8px 0; padding: 1rem 1.2rem; margin-bottom: 0.8rem;
}
.nba-card.suppressed {
    border-left-color: #BDBDBD; background: #F5F5F5; opacity: 0.75;
}
.nba-card .action-name { font-size: 1rem; font-weight: 600; margin-bottom: 0.3rem; }
.nba-card .detail { font-size: 0.82rem; color: #424242; line-height: 1.5; }
.nba-card .detail .muted { color: #9E9E9E; }

/* Timeline */
.tl-item { border-left: 3px solid #E0E0E0; padding: 0.5rem 0 0.5rem 1rem; margin-bottom: 0.2rem; }
.tl-item.interaction { border-left-color: #1565C0; }
.tl-item.claim       { border-left-color: #D32F2F; }
.tl-item.policy      { border-left-color: #388E3C; }
.tl-item.billing     { border-left-color: #F57C00; }
.tl-item.digital     { border-left-color: #7B1FA2; }
.tl-item.quote       { border-left-color: #00838F; }
.tl-date { font-size: 0.72rem; color: #9E9E9E; }
.tl-desc { font-size: 0.85rem; color: #212121; margin-top: 0.1rem; }
.tl-badge { font-size: 0.68rem; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def q(sql):
    return session.sql(sql).to_pandas()

def churn_color(score):
    if score >= 0.5: return RED
    if score >= 0.3: return AMBER
    return GREEN

def churn_bar(score, width="100%"):
    color = churn_color(score)
    pct = min(score * 100, 100)
    return f"""<div class="churn-bar-bg" style="width:{width}">
        <div class="churn-bar-fill" style="width:{pct}%;background:{color}"></div>
    </div>"""

def badge(text, variant="grey"):
    return f'<span class="badge badge-{variant}">{text}</span>'


# ─── Navigation state ──────────────────────────────────────────────
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Worklist"


# ─── Tabs ───────────────────────────────────────────────────────────
tab0, tab1, tab2, tab3 = st.tabs(["How it works", "Worklist", "Customer 360", "Governance"])


# =====================================================================
# TAB 0: HOW IT WORKS
# =====================================================================
with tab0:
    st.markdown("#### How Meridian 360 works")
    st.caption("A Customer 360 and Next Best Action engine for a P&C insurer. "
               "All data is synthetic. Read this tab first, then work left to right.")

    st.markdown("""
**The flow:** policy, claim, billing, web and call-transcript data is unified per customer →
Cortex AI reads every call transcript → a transparent churn model scores each customer →
the NBA engine proposes actions → 12 suppression rules block the unsafe ones → you act.
""")

    st.divider()
    st.markdown("##### 1. Worklist: who needs attention this week")
    st.markdown("""
Every customer renewing in the next 45 days who shows churn risk, ranked by **expected loss**
(churn risk × annual premium). Tick the checkbox to rank by raw churn risk instead.

| Column | Meaning |
|---|---|
| **Renews in** | Days until the nearest policy renewal (e.g. `5d`) |
| **Churn risk** | Probability-style score 0–100% from 9 weighted signals; bar is green < 30%, amber 30–50%, red ≥ 50% |
| **Annual premium** | Total premium across the customer's active policies |
| **Expected loss** | Churn risk × premium: the revenue at stake if nobody acts |
| **Signals** | How many of the 9 churn signals are firing |
| **Cross-sell gap** | Product the household is missing (HOME, AUTO, UMBRELLA) |

**Example:** *Jennifer Moore · 5d · 48% · 74,913 · 35,958 · 3 signals · UMBRELLA* means she renews in
5 days, has a 48% churn risk on 74,913 of premium, so about 35,958 is at risk. Three signals are firing,
and her household has no umbrella cover. Click **View** and open the Customer 360 tab.
""")

    st.divider()
    st.markdown("##### 2. Customer 360: everything about one customer")
    st.markdown("""
- **Header:** tenure, premium, churn risk, renewal countdown, and red/amber warning badges
  (open claim, competitor shopping, churn language, rate shock, cancellation browsing).
- **Sentiment trajectory:** AI-scored sentiment of each phone call over time. A falling line is a churn warning.
- **Ask me anything:** plain-English what / why / how questions, answered by Cortex AI from
  call transcripts plus portfolio statistics, with citations. Scope it to this customer or the whole book.
- **Timeline:** every policy, claim, billing, call, web and quote event in one stream.
- **Next Best Actions:** recommended actions with reason, expected value, urgency and SLA, plus an
  **Execute** button that logs the action. Suppressed actions are shown greyed out with the rule that blocked them.

**Example:** pick **Arjun Mehta (CUST-00001)**. He has a 27.5% premium increase, a 74-day open claim,
three calls with sentiment falling 0.38 → 0.18 → 0.04, and a competitor quote 13,000 cheaper.
The engine recommends a Supervisor Rate Review and a Win-Back call, and **suppresses** the Home Bundle
Cross-Sell because rule S01 forbids selling to someone with an open claim.
Try asking: *"Why is this customer likely to leave?"*
""")

    st.divider()
    st.markdown("##### 3. Governance: proof the guardrails work")
    st.markdown("""
- **Suppression audit:** for each rule, how many actions it blocked, how many customers, and the
  expected value deliberately given up to stay compliant.
- **AI enrichment QA:** parse rate and counts of churn signals, complaints and competitor mentions
  extracted from 630 transcripts.
- **Rule book:** all 12 suppression rules with their scope, trigger condition and rationale.

**Example:** the S01 row shows every cross-sell blocked because the customer had an open claim. That
revenue was given up on purpose, and nothing in it was recommended.
""")


# =====================================================================
# TAB 1: WORKLIST
# =====================================================================
with tab1:
    st.markdown("#### Retention Worklist")
    st.caption("Customers renewing within 45 days, ranked by actionable risk")

    sort_col = st.checkbox("Sort by churn risk (instead of expected loss)", value=False)
    order_col = "RANK_CHURN_RISK" if sort_col else "RANK_EXPECTED_LOSS"

    wl = q(f"""
        SELECT PARTY_ID, FIRST_NAME || ' ' || LAST_NAME AS NAME,
               NEAREST_RENEWAL_DAYS, CHURN_RISK_SCORE, TOTAL_PREMIUM,
               EXPECTED_LOSS, NUM_SIGNALS, PRIMARY_CROSS_SELL_LOB,
               RANK_EXPECTED_LOSS, RANK_CHURN_RISK
        FROM MERIDIAN.SERVING.V_RETENTION_WORKLIST
        ORDER BY {order_col}
    """)

    if wl.empty:
        st.info("No customers with upcoming renewals and churn risk.")
    else:
        widths = [0.25, 0.08, 0.12, 0.12, 0.12, 0.08, 0.08, 0.15]
        hdr = st.columns(widths)
        headers = [
            ("Customer", "Name and customer ID"),
            ("Renews in", "Days until the nearest policy renewal"),
            ("Churn risk", "0-100% score from 9 weighted signals. Green <30%, amber 30-50%, red >=50%"),
            ("Annual premium", "Total premium across active policies"),
            ("Expected loss", "Churn risk x annual premium: revenue at stake if nobody acts"),
            ("Signals", "How many of the 9 churn signals are firing"),
            ("Cross-sell", "Product the household is missing"),
            ("", ""),
        ]
        for col, (label, tip) in zip(hdr, headers):
            if label:
                col.markdown(f"<span style='font-size:0.75rem;color:#757575;text-transform:uppercase;"
                             f"letter-spacing:0.05em;font-weight:600' title='{tip}'>{label}</span>",
                             unsafe_allow_html=True)
        st.caption("Hover a column header for its definition. Expected loss = churn risk x annual premium.")

        for _, row in wl.iterrows():
            with st.container():
                cols = st.columns(widths)
                cols[0].markdown(f"**{row['NAME']}**<br><span style='color:#9E9E9E;font-size:0.75rem'>{row['PARTY_ID']}</span>", unsafe_allow_html=True)
                cols[1].markdown(f"**{int(row['NEAREST_RENEWAL_DAYS'])}d**")
                score = float(row['CHURN_RISK_SCORE'] or 0)
                cols[2].markdown(f"{score:.0%}{churn_bar(score)}", unsafe_allow_html=True)
                cols[3].markdown(f"**{row['TOTAL_PREMIUM']:,.0f}**")
                cols[4].markdown(f"**{row['EXPECTED_LOSS']:,.0f}**")
                cols[5].markdown(f"{int(row['NUM_SIGNALS'])} signals")
                xsell = row.get('PRIMARY_CROSS_SELL_LOB')
                if xsell:
                    cols[6].markdown(badge(xsell, "blue"), unsafe_allow_html=True)
                else:
                    cols[6].markdown("—")
                if cols[7].button("View", key=f"wl_{row['PARTY_ID']}", use_container_width=True):
                    st.session_state.selected_customer = row['PARTY_ID']
                    st.info(f"**{row['NAME']}** selected — switch to the **Customer 360** tab above to see their full profile.")
                st.divider()


# =====================================================================
# TAB 2: CUSTOMER 360
# =====================================================================
with tab2:
    customers = q("""
        SELECT PARTY_ID, FIRST_NAME || ' ' || LAST_NAME || '  (' || PARTY_ID || ')' AS LABEL
        FROM MERIDIAN.SERVING.CUSTOMER_360
        ORDER BY PARTY_ID
    """)
    options = customers['LABEL'].tolist()
    ids = customers['PARTY_ID'].tolist()

    preselect = st.session_state.selected_customer or "CUST-00001"
    default_idx = ids.index(preselect) if preselect in ids else 0

    selected_label = st.selectbox("Customer", options, index=default_idx)
    cust_id = ids[options.index(selected_label)]

    if not cust_id:
        st.info("Select a customer from the Worklist tab or enter an ID above.")
    else:
        cust = q(f"SELECT * FROM MERIDIAN.SERVING.CUSTOMER_360 WHERE PARTY_ID = '{cust_id}'")
        if cust.empty:
            st.warning(f"Customer {cust_id} not found.")
        else:
            c = cust.iloc[0]

            # ── Profile header ──
            h1, h2, h3 = st.columns([0.4, 0.35, 0.25])
            with h1:
                st.markdown(f"### {c['FIRST_NAME']} {c['LAST_NAME']}")
                st.caption(f"{cust_id}  ·  {c['STATE']}  ·  Household {c['HOUSEHOLD_ID']}")
                badges_html = ""
                if c.get('OPEN_CLAIMS', 0) > 0:
                    badges_html += badge(f"Open claim ({int(c.get('MAX_CLAIM_DAYS_OPEN', 0))}d)", "red")
                if c.get('SIG_COMPETITOR_MENTION', 0) > 0:
                    badges_html += badge("Competitor shopping", "red")
                if c.get('SIG_CHURN_LANGUAGE', 0) > 0:
                    badges_html += badge("Churn language", "amber")
                if c.get('SIG_RATE_SHOCK', 0) > 0:
                    badges_html += badge("Rate shock", "amber")
                if c.get('RECENT_CANCEL_PAGES', 0) > 0:
                    badges_html += badge("Cancellation browsing", "amber")
                if badges_html:
                    st.markdown(badges_html, unsafe_allow_html=True)

            with h2:
                score = float(c.get('CHURN_RISK_SCORE', 0) or 0)
                st.markdown(f"""
                <div class="metric-row">
                    <div class="metric-card"><div class="label">Tenure</div><div class="value">{c['TENURE_YEARS']:.0f}yr</div></div>
                    <div class="metric-card"><div class="label">Premium</div><div class="value">{c['TOTAL_PREMIUM']:,.0f}</div></div>
                    <div class="metric-card"><div class="label">Churn Risk</div>
                        <div class="value" style="color:{churn_color(score)}">{score:.0%}</div>
                        {churn_bar(score, "80%")}
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with h3:
                renewal = c.get('NEAREST_RENEWAL_DAYS')
                if renewal is not None and int(renewal) <= 45:
                    st.markdown(f"""
                    <div class="metric-card" style="border-color:{AMBER}">
                        <div class="label">Renewal in</div>
                        <div class="value" style="color:{AMBER}">{int(renewal)} days</div>
                    </div>""", unsafe_allow_html=True)
                st.markdown(f"""
                <div class="metric-card" style="margin-top:0.5rem">
                    <div class="label">Policies / LOBs</div>
                    <div class="value">{int(c['POLICY_COUNT'])} / {int(c['LOB_COUNT'])}</div>
                </div>""", unsafe_allow_html=True)

            st.divider()

            # ── Sentiment trajectory ──
            sent_data = q(f"""
                SELECT i.INTERACTION_DATE, ai.AI_SENTIMENT_SCORE, ai.AI_SENTIMENT_LABEL,
                       ai.AI_SUMMARY, ai.AI_KEY_QUOTE, ai.AI_COMPETITOR_MENTIONED
                FROM MERIDIAN.ENRICHED.INTERACTION_AI ai
                JOIN MERIDIAN.CURATED.DT_INTERACTION i ON ai.INTERACTION_ID = i.INTERACTION_ID
                WHERE ai.PARTY_ID = '{cust_id}' AND ai.PARSE_SUCCESS = TRUE
                ORDER BY i.INTERACTION_DATE
            """)

            if not sent_data.empty and len(sent_data) >= 2:
                st.markdown("##### Sentiment Trajectory")
                sent_data = sent_data.sort_values('INTERACTION_DATE', ascending=True).reset_index(drop=True)
                dates = sent_data['INTERACTION_DATE']
                scores = [float(s) for s in sent_data['AI_SENTIMENT_SCORE']]
                labels = [d.strftime('%b %d') if hasattr(d, 'strftime') else str(d)[:10] for d in dates]
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=labels,
                    y=scores,
                    mode='lines+markers+text',
                    line=dict(color=BLUE, width=2),
                    marker=dict(size=12, color=[churn_color(1.0 - s) for s in scores],
                                line=dict(width=2, color='white')),
                    text=[f"{s:.2f}" for s in scores],
                    textposition='top center',
                    textfont=dict(size=11),
                    hovertemplate='%{x}<br>Sentiment: %{y:.2f}<extra></extra>'
                ))
                fig.add_hline(y=0.3, line_dash="dash", line_color=RED, opacity=0.4,
                              annotation_text="Negative threshold", annotation_position="bottom right")
                fig.update_layout(
                    height=250, margin=dict(l=0, r=0, t=30, b=0),
                    yaxis=dict(range=[0, 1], title="Sentiment", gridcolor="#F0F0F0"),
                    xaxis=dict(title="", type='category', gridcolor="#F0F0F0"),
                    plot_bgcolor="white", paper_bgcolor="white",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.divider()

            # ── Ask me anything (Cortex Search RAG + portfolio stats) ──
            st.markdown("##### Ask me anything: what? why? how?")
            st.caption("Plain-English questions about this customer, the customer base, or customer behaviour. "
                       "Answers come from call transcripts and portfolio statistics, with citations.")
            scope = st.radio("Scope", ["This customer", "All customers"], horizontal=True, key="ask_scope")
            user_q = st.text_input(
                "Question",
                placeholder=("e.g. Why is this customer likely to leave?  ·  What do angry customers complain about?  ·  "
                             "How many customers mention a competitor?"),
                key="ask_box",
            )
            if user_q:
                # Cortex Search payload in a $$-quoted literal so JSON escapes survive SQL parsing
                payload = {
                    "query": user_q.replace("$$", ""),
                    "columns": ["INTERACTION_ID", "PARTY_ID", "SUMMARY", "AI_SENTIMENT_LABEL",
                                "AI_KEY_QUOTE", "AI_COMPETITOR_MENTIONED", "TOPIC"],
                    "limit": 5 if scope == "This customer" else 8,
                }
                if scope == "This customer":
                    payload["filter"] = {"@eq": {"PARTY_ID": cust_id}}
                search_result = session.sql(
                    "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('MERIDIAN.INTELLIGENCE.INTERACTION_SEARCH', "
                    f"$${json.dumps(payload)}$$)::VARCHAR AS RESULTS"
                ).collect()[0]['RESULTS']
                sources = json.loads(search_result).get('results', [])

                stats = q("""
                    SELECT COUNT(*) AS CUSTOMERS,
                           ROUND(AVG(CHURN_RISK_SCORE), 3) AS AVG_CHURN_RISK,
                           SUM(IFF(CHURN_RISK_SCORE >= 0.5, 1, 0)) AS HIGH_RISK,
                           SUM(IFF(OPEN_CLAIMS > 0, 1, 0)) AS WITH_OPEN_CLAIM,
                           SUM(IFF(SIG_RATE_SHOCK > 0, 1, 0)) AS WITH_RATE_SHOCK,
                           SUM(IFF(SIG_COMPETITOR_MENTION > 0, 1, 0)) AS MENTIONED_COMPETITOR,
                           SUM(IFF(SIG_CHURN_LANGUAGE > 0, 1, 0)) AS USED_CHURN_LANGUAGE,
                           SUM(IFF(SIG_NEGATIVE_SENTIMENT > 0, 1, 0)) AS NEGATIVE_SENTIMENT,
                           SUM(IFF(SIG_PAYMENT_DISTRESS > 0, 1, 0)) AS PAYMENT_DISTRESS,
                           SUM(IFF(LOB_COUNT <= 1, 1, 0)) AS MONO_LINE,
                           ROUND(SUM(TOTAL_PREMIUM), 0) AS TOTAL_PREMIUM,
                           ROUND(SUM(CHURN_RISK_SCORE * TOTAL_PREMIUM), 0) AS PREMIUM_AT_RISK
                    FROM MERIDIAN.SERVING.CUSTOMER_360
                """).iloc[0].to_dict()
                actions = q("""
                    SELECT ACTION_NAME, STATUS, COUNT(*) AS N
                    FROM MERIDIAN.SERVING.NBA_RECOMMENDATION GROUP BY 1, 2 ORDER BY 1, 2
                """)
                stats_block = "; ".join(f"{k}={v}" for k, v in stats.items())
                actions_block = "; ".join(f"{a['ACTION_NAME']} {a['STATUS']}={a['N']}" for _, a in actions.iterrows())

                profile_block = ""
                if scope == "This customer":
                    cust_nbas = q(f"""
                        SELECT ACTION_NAME, STATUS, SUPPRESSION_RULE_NAME
                        FROM MERIDIAN.SERVING.NBA_RECOMMENDATION WHERE PARTY_ID = '{cust_id}'
                    """)
                    nba_list = ", ".join(
                        f"{n['ACTION_NAME']} ({n['STATUS']}"
                        f"{' by ' + n['SUPPRESSION_RULE_NAME'] if n['SUPPRESSION_RULE_NAME'] else ''})"
                        for _, n in cust_nbas.iterrows())
                    profile_block = (
                        f"\n\n[CUSTOMER PROFILE] {cust_id}: tenure {c['TENURE_YEARS']} years, premium {c['TOTAL_PREMIUM']}, "
                        f"churn risk {c['CHURN_RISK_SCORE']}, reason codes {list(c['CHURN_REASON_CODES'] or [])}, "
                        f"renewal in {c['NEAREST_RENEWAL_DAYS']} days, open claims {c['OPEN_CLAIMS']}, "
                        f"longest claim open {c['MAX_CLAIM_DAYS_OPEN']} days, lines of business {c['LOB_COUNT']}. "
                        f"Actions: {nba_list or 'none'}."
                    )

                context_block = "\n\n".join([
                    f"Source {j+1} [{src['INTERACTION_ID']}] (customer {src.get('PARTY_ID','')}): {src.get('SUMMARY','')} "
                    f"Sentiment: {src.get('AI_SENTIMENT_LABEL','')}. "
                    f"Key quote: {src.get('AI_KEY_QUOTE','')}"
                    f"{(' Competitor mentioned: ' + src['AI_COMPETITOR_MENTIONED']) if src.get('AI_COMPETITOR_MENTIONED') else ''}"
                    for j, src in enumerate(sources)
                ]) or "No matching call interactions."
                prompt = (
                    "You are a customer intelligence analyst for Meridian, a P&C insurer. "
                    "Answer what / why / how questions about customers and their behaviour using ONLY the context below: "
                    "portfolio statistics, the action summary, the customer profile if present, and retrieved call interactions. "
                    "Cite call evidence as [INTERACTION_ID], statistics as [PORTFOLIO STATS], and profile facts as [CUSTOMER PROFILE]. "
                    "If the context does not contain enough information, say so explicitly. Do not invent anything.\n\n"
                    f"Question: {user_q}\n\n"
                    f"[PORTFOLIO STATS] {stats_block}\n\n[ACTION SUMMARY] {actions_block}"
                    f"{profile_block}\n\nCall interactions:\n{context_block}"
                )
                answer = session.sql(
                    "SELECT AI_COMPLETE('claude-sonnet-4-5', ?)::VARCHAR AS ANSWER", params=[prompt]
                ).collect()[0]['ANSWER']

                st.markdown(answer)
                if sources:
                    with st.expander(f"Cited sources ({len(sources)} interactions)"):
                        for src in sources:
                            sent_badge = badge(src.get('AI_SENTIMENT_LABEL',''), 'red' if src.get('AI_SENTIMENT_LABEL') == 'NEGATIVE' else 'green')
                            st.markdown(f"""
                            <div class="tl-item interaction">
                                <b>{src['INTERACTION_ID']}</b> · {src.get('PARTY_ID','')} · {src.get('TOPIC','')} {sent_badge}<br>
                                <span style="font-size:0.85rem">{src.get('SUMMARY','')}</span><br>
                                <span style="font-style:italic;color:#757575;font-size:0.82rem">\"{src.get('AI_KEY_QUOTE','')}\"</span>
                            </div>""", unsafe_allow_html=True)
                st.divider()

            # ── Timeline ──
            col_tl, col_nba = st.columns([0.55, 0.45])

            with col_tl:
                st.markdown("##### Timeline")
                timeline = q(f"""
                    SELECT EVENT_TS, EVENT_TYPE, CATEGORY, DESCRIPTION
                    FROM MERIDIAN.SERVING.CUSTOMER_TIMELINE
                    WHERE PARTY_ID = '{cust_id}'
                    ORDER BY EVENT_TS DESC
                    LIMIT 30
                """)
                ai_lookup = {}
                if not sent_data.empty:
                    for _, r in sent_data.iterrows():
                        ai_lookup[str(r.get('INTERACTION_DATE',''))[:19]] = r

                for _, ev in timeline.iterrows():
                    cat = str(ev['CATEGORY']).lower()
                    desc = ev['DESCRIPTION'] or ''
                    ts = str(ev['EVENT_TS'])[:16]
                    badges_str = ""
                    if '[RATE SHOCK]' in desc:
                        badges_str += badge("RATE SHOCK", "red")
                        desc = desc.replace(' [RATE SHOCK]', '')
                    if '[RISK PAGE]' in desc:
                        badges_str += badge("RISK PAGE", "amber")
                        desc = desc.replace(' [RISK PAGE]', '')

                    st.markdown(f"""
                    <div class="tl-item {cat}">
                        <span class="tl-date">{ts}</span> {badges_str}
                        <div class="tl-desc">{desc}</div>
                    </div>""", unsafe_allow_html=True)

            # ── NBA Panel ──
            with col_nba:
                st.markdown("##### Next Best Actions")
                nbas = q(f"""
                    SELECT * FROM MERIDIAN.SERVING.NBA_RECOMMENDATION
                    WHERE PARTY_ID = '{cust_id}'
                    ORDER BY RANK_FOR_CUSTOMER
                """)

                recommended = nbas[nbas['STATUS'] == 'RECOMMENDED'].drop_duplicates(subset=['ACTION_TYPE'])
                suppressed = nbas[nbas['STATUS'] == 'SUPPRESSED']

                if recommended.empty and suppressed.empty:
                    st.info("No actions generated for this customer.")
                else:
                    for _, act in recommended.iterrows():
                        supervisor_badge = ""
                        if act.get('NEEDS_SUPERVISOR'):
                            supervisor_badge = f' {badge("Supervisor approval required", "amber")}'
                        ev_ref = f"Evidence: {act['EVIDENCE_REF']}" if act.get('EVIDENCE_REF') else ""
                        st.markdown(f"""
                        <div class="nba-card">
                            <div class="action-name">{act['ACTION_NAME']}{supervisor_badge}</div>
                            <div class="detail">
                                {act['REASON_TEXT']}<br>
                                <span class="muted">Category:</span> {act['CATEGORY']}
                                · <span class="muted">Channel:</span> {act['CHANNEL']}
                                · <span class="muted">EV:</span> {act['EXPECTED_VALUE']:,.0f}
                                · <span class="muted">Urgency:</span> {act['URGENCY']:.1f}
                                · <span class="muted">SLA:</span> {int(act['SLA_DAYS'])}d<br>
                                {f'<span class="muted">{ev_ref}</span>' if ev_ref else ''}
                            </div>
                        </div>""", unsafe_allow_html=True)

                        if st.button(f"Execute: {act['ACTION_NAME']}", key=f"exec_{act['ACTION_TYPE']}_{cust_id}"):
                            result = session.sql(f"""
                                CALL MERIDIAN.APP.SP_EXECUTE_ACTION(
                                    '{cust_id}', '{act['ACTION_TYPE']}', CURRENT_USER()
                                )
                            """).collect()[0][0]
                            import json as _json
                            r = _json.loads(result) if isinstance(result, str) else result
                            if r.get('success'):
                                slack = r.get('slack_status', 'UNKNOWN')
                                st.success(f"{r['action_name']} executed and logged (ID: {r['log_id'][:8]}...)")
                                if slack == 'SIMULATED':
                                    st.info("Slack notification simulated (external access not available on trial account). Message payload logged.")
                                elif slack.startswith('FAILED'):
                                    st.warning(f"Action logged successfully, but Slack notification failed: {slack}")
                            else:
                                st.error(r.get('error', 'Unknown error'))

                    if not suppressed.empty:
                        st.markdown("---")
                        st.markdown(f"<span style='color:{GREY};font-size:0.85rem;font-weight:600'>Suppressed Actions</span>", unsafe_allow_html=True)
                        supp_grouped = suppressed.groupby('ACTION_TYPE').first().reset_index()
                        supp_rules = suppressed.groupby('ACTION_TYPE').apply(
                            lambda g: list(zip(g['SUPPRESSION_RULE_ID'], g['SUPPRESSION_RULE_NAME'], g['SUPPRESSION_REASON']))
                        ).to_dict()

                        for _, act in supp_grouped.iterrows():
                            rules_html = ""
                            for rid, rname, reason in supp_rules.get(act['ACTION_TYPE'], []):
                                rules_html += f'<br>{badge(rid, "grey")} <b>{rname}</b>: {reason}'
                            st.markdown(f"""
                            <div class="nba-card suppressed">
                                <div class="action-name" style="color:{GREY}">{act['ACTION_NAME']} {badge("SUPPRESSED", "grey")}</div>
                                <div class="detail">
                                    {act['REASON_TEXT']}<br>
                                    <span class="muted">Would-be EV:</span> {act['EXPECTED_VALUE']:,.0f}<br>
                                    <b>Blocked by:</b>{rules_html}
                                </div>
                            </div>""", unsafe_allow_html=True)


# =====================================================================
# TAB 3: GOVERNANCE
# =====================================================================
with tab3:
    st.markdown("#### Governance Dashboard")

    # ── Suppression audit ──
    st.markdown("##### Suppression Audit")
    st.caption("Actions deliberately blocked by each rule, and the expected value forgone")
    audit = q("SELECT * FROM MERIDIAN.SERVING.V_SUPPRESSION_AUDIT ORDER BY EXPECTED_VALUE_FORGONE DESC")
    if not audit.empty:
        st.dataframe(
            audit.rename(columns={
                "SUPPRESSION_RULE_ID": "Rule",
                "SUPPRESSION_RULE_NAME": "Rule Name",
                "ACTIONS_BLOCKED": "Actions Blocked",
                "CUSTOMERS_AFFECTED": "Customers",
                "EXPECTED_VALUE_FORGONE": "EV Forgone",
                "AVG_CHURN_RISK_BLOCKED": "Avg Churn Risk",
            }),
            use_container_width=True,
        )

    st.divider()

    # ── Enrichment QA ──
    st.markdown("##### AI Enrichment QA")
    qa = q("""
        SELECT
            COUNT(*) AS TOTAL,
            SUM(PARSE_SUCCESS::INT) AS PARSED,
            SUM(AI_CHURN_SIGNAL::INT) AS CHURN_SIGNALS,
            SUM(AI_COMPLAINT_FLAG::INT) AS COMPLAINTS,
            SUM(CASE WHEN AI_COMPETITOR_MENTIONED IS NOT NULL AND AI_COMPETITOR_MENTIONED != '' THEN 1 ELSE 0 END) AS COMPETITOR_MENTIONS,
            SUM(AI_RESOLVED_ON_CALL::INT) AS RESOLVED_ON_CALL
        FROM MERIDIAN.ENRICHED.INTERACTION_AI
    """)
    if not qa.empty:
        r = qa.iloc[0]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Parse Rate", f"{int(r['PARSED'])}/{int(r['TOTAL'])}")
        m2.metric("Churn Signals", int(r['CHURN_SIGNALS']))
        m3.metric("Complaints", int(r['COMPLAINTS']))
        m4.metric("Competitor Mentions", int(r['COMPETITOR_MENTIONS']))
        m5.metric("Resolved on Call", int(r['RESOLVED_ON_CALL']))

    intents = q("""
        SELECT AI_PRIMARY_INTENT AS INTENT, COUNT(*) AS CNT
        FROM MERIDIAN.ENRICHED.INTERACTION_AI
        WHERE PARSE_SUCCESS GROUP BY 1 ORDER BY CNT DESC
    """)
    if not intents.empty:
        st.bar_chart(intents.set_index('INTENT'), height=250)

    st.divider()

    # ── Rule book ──
    st.markdown("##### Suppression Rule Book")
    rules = [
        ("S01", "Open-claim freeze", "CROSS_SELL", "Party has an open or reopened claim", "Soliciting during an active claim creates conflict of interest"),
        ("S02", "Litigation hold", "ALL", "At-fault open claim with reserves > 2x paid", "Automated outreach could prejudice the insurer's legal position"),
        ("S03", "Recent denial cooling-off", "CROSS_SELL", "Claim denied within last 90 days", "Selling coverage after denial is tone-deaf and risks regulatory complaints"),
        ("S04", "Collections status", "CROSS_SELL + LOYALTY", "Any billing in COLLECTIONS", "Marketing to collections customers may violate debt-collection regulations"),
        ("S05", "Cancellation in progress", "CROSS_SELL", "Cancellation request in last 14 days", "Pushing new products before resolving cancellation driver feels coercive"),
        ("S06", "Regulatory blackout", "RENEWAL OFFERS", "State with active rate-freeze moratorium", "Post-catastrophe moratoriums prohibit rate actions"),
        ("S07", "Minor party", "ALL MARKETING", "Customer under 18", "Minors cannot enter insurance contracts"),
        ("S08", "Duplicate action cooldown", "SAME ACTION", "Same action executed within 30 days", "Prevents spamming the same recommendation"),
        ("S09", "Negative-sentiment active conversation", "CROSS_SELL", "Negative + unresolved interaction in 7 days", "Selling to actively upset customer escalates the situation"),
        ("S10", "Premium-shock grace period", "CROSS_SELL", "Premium increase > 15% on pending renewal", "Customer just absorbed a price shock — allow 30 days to settle"),
        ("S11", "Excessive contact frequency", "ALL NON-URGENT", "3+ outbound contacts in 14 days", "Over-contact erodes trust and risks TCPA violations"),
        ("S12", "Do-not-contact flag", "ALL", "Customer opted out", "Legally required under CAN-SPAM, TCPA, and state privacy laws"),
    ]
    for rid, name, scope, condition, rationale in rules:
        with st.expander(f"{rid} — {name}"):
            st.markdown(f"**Scope:** {scope}")
            st.markdown(f"**Condition:** {condition}")
            st.markdown(f"**Rationale:** {rationale}")
