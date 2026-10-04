#!/usr/bin/env python3
"""
gen_synth.py — Meridian 360 Synthetic Data Generator

Produces referentially consistent CSVs for all RAW tables.
Deterministic: fixed seed, re-running produces identical output.
Transcripts are causally linked to structured data via a tone parameter.
Hero customer CUST-00001 is hand-authored after purging random data.
"""

import csv
import os
import random
from datetime import date, datetime, timedelta
from collections import defaultdict

# ─── Configuration ──────────────────────────────────────────────────
SEED = 42
TODAY = date.today()
NOW = datetime.now().replace(second=0, microsecond=0)
NUM_PARTIES = 500
NUM_HOUSEHOLDS = 310

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ─── Static reference data ──────────────────────────────────────────
FIRST_NAMES = [
    "James", "Robert", "Michael", "David", "Richard", "Thomas", "Charles",
    "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Paul", "Andrew",
    "Joshua", "Kenneth", "Kevin", "Brian", "George", "Timothy",
    "Raj", "Amit", "Vikram", "Sanjay", "Arjun", "Deepak", "Suresh",
    "Rahul", "Nikhil", "Arun", "Mary", "Patricia", "Jennifer", "Linda",
    "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen",
    "Lisa", "Nancy", "Betty", "Margaret", "Sandra", "Ashley", "Dorothy",
    "Kimberly", "Emily", "Donna", "Priya", "Anita", "Sunita", "Kavita",
    "Lakshmi", "Meera", "Pooja", "Neha", "Divya", "Anjali",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Hernandez", "Moore", "Martin", "Jackson", "Thompson", "White", "Lopez",
    "Patel", "Shah", "Kumar", "Singh", "Sharma", "Gupta", "Reddy",
    "Nair", "Rao", "Iyer",
]
STATES = [
    "CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]
STREETS = [
    "Main St", "Oak Ave", "Maple Dr", "Cedar Ln", "Elm St", "Park Ave",
    "Washington Blvd", "Lake Dr", "Hill Rd", "Forest Way", "Valley View",
    "Sunset Blvd", "River Rd", "Spring St", "Church St", "High St",
]
COMPETITORS = [
    "Kavach General", "ShieldFirst Insurance", "SafeHaven Mutual",
    "Guardian Alliance", "TrustBridge Insurance", "Pinnacle Coverage",
]
PREMIUM_RANGES = {
    "AUTO": (15000, 55000), "HOME": (10000, 40000),
    "UMBRELLA": (3000, 10000), "RENTERS": (2000, 8000),
}
DEDUCTIBLE_RANGES = {
    "AUTO": (500, 5000), "HOME": (1000, 10000),
    "UMBRELLA": (0, 0), "RENTERS": (250, 2500),
}
COVERAGE_RANGES = {
    "AUTO": (50000, 500000), "HOME": (100000, 1000000),
    "UMBRELLA": (500000, 5000000), "RENTERS": (20000, 100000),
}

# ─── Helpers ────────────────────────────────────────────────────────
def fid(prefix, n, w=5):
    return f"{prefix}-{n:0{w}d}"

def rdate(start, end):
    d = (end - start).days
    return start + timedelta(days=random.randint(0, max(d, 0)))

def rdatetime(start, end):
    d = rdate(start, end)
    return datetime(d.year, d.month, d.day, random.randint(8, 18), random.randint(0, 59), random.randint(0, 59))

def rphone():
    return f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"

def remail(first, last):
    dom = random.choice(["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"])
    return f"{first.lower()}.{last.lower()}{random.randint(1,99)}@{dom}"

def raddr():
    return f"{random.randint(100,9999)} {random.choice(STREETS)}"

def rzip():
    return f"{random.randint(10000,99999)}"

def fval(v):
    if v is None: return ""
    if isinstance(v, datetime): return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date): return v.strftime("%Y-%m-%d")
    return str(v)


# ═══════════════════════════════════════════════════════════════════
# TRANSCRIPT TEMPLATES — keyed by (category, tone)
# ═══════════════════════════════════════════════════════════════════

T_PREMIUM = {
    "concerned": [
        "Hello, I'm calling about my {lob} policy {pid}. I received my renewal notice and the premium is going up from {old:,.0f} to {new:,.0f}. That's about {pct:.0f} percent more. I've been with you {tenure} years and I'd appreciate an explanation.",
        "Hi, I just got my renewal for {pid} and the new premium of {new:,.0f} caught me off guard. It was {old:,.0f} before. Can you review my account?",
    ],
    "frustrated": [
        "I need to talk to someone about my renewal for {pid}. A {pct:.0f} percent increase from {old:,.0f} to {new:,.0f} is unacceptable. I have no claims and nothing has changed. Why are my rates going up this much?",
        "This is ridiculous. My {lob} policy {pid} premium jumped from {old:,.0f} to {new:,.0f}. That's {delta:,.0f} more per year. I've been a customer for {tenure} years and I expect better.",
    ],
    "angry": [
        "I'm furious about my renewal notice. Policy {pid}, you're asking {new:,.0f} when I was paying {old:,.0f}? A {pct:.0f} percent jump after {tenure} years and not a single claim? I want to speak to a supervisor.",
        "Unbelievable. {new:,.0f} for my {lob} policy? I just saw my renewal for {pid}. A {pct:.0f} percent increase with a clean record. I feel completely taken advantage of.",
    ],
    "threatening": [
        "I'm calling one last time about {pid}. You've raised my {lob} premium to {new:,.0f}, a {pct:.0f} percent increase. I've already gotten a quote from {comp} for {comp_prem:,.0f} — that's {savings:,.0f} less. If you can't match it, I'm switching today.",
        "I want you to know I'm actively shopping. {comp} quoted me {comp_prem:,.0f} for the same {lob} coverage you want {new:,.0f} for under {pid}. That's {savings:,.0f} I'd save. After {tenure} years, you're making it easy to leave.",
    ],
}
T_CLAIM = {
    "concerned": [
        "Hi, I'm calling about claim {cid}. It's been {days} days since I filed and I haven't heard much. Can you give me an update?",
        "Hello, I'd like to check on claim {cid}. I filed it {days} days ago for {ctype} and I'm wondering when to expect a resolution.",
    ],
    "frustrated": [
        "This is my second call about claim {cid}. It's been {days} days with no resolution. Every time I call I get told it's under review. What's the holdup?",
        "I'm getting really frustrated with claim {cid}. {days} days, no updates, no communication. When is someone going to handle this?",
    ],
    "angry": [
        "I am extremely upset about claim {cid}. {days} days! I was not at fault and yet I'm suffering. No one returns my calls. This is completely unacceptable.",
        "Claim {cid} has been open for {days} days. I've called multiple times, been transferred, promised callbacks that never happen. I'm at my wit's end.",
    ],
    "threatening": [
        "I'm done waiting on claim {cid}. {days} days for a straightforward {ctype} claim where I'm not at fault. I've spoken to a lawyer and I'm looking at other insurers.",
        "Let me be clear about claim {cid}. {days} days, not at fault, adjuster unreachable. I've filed a complaint with the state insurance department.",
    ],
}
T_BILLING = {
    "concerned": [
        "Hi, I'm calling about a billing issue on policy {pid}. I see a charge that doesn't match what I expected. Can you help?",
        "Hello, I noticed my payment of {amt:,.0f} didn't go through for {pid}. I want to make sure my coverage isn't affected.",
    ],
    "frustrated": [
        "I've been trying to resolve a billing issue for {pid} for weeks. I keep getting different answers. My payment was {amt:,.0f} and now you say I owe more.",
        "Why is my account past due when I made a payment of {amt:,.0f} for {pid}? I have the confirmation. Someone on your end messed up.",
    ],
}
T_CANCEL = {
    "frustrated": [
        "I'd like to discuss cancelling my {lob} policy {pid}. Between the rate increases and the service level, I'm not sure it's worth staying.",
        "I'm considering cancelling. My {lob} policy {pid} is too expensive and I've seen better rates elsewhere.",
    ],
    "angry": [
        "I want to cancel policy {pid} effective immediately. The premium increase was the last straw. I've already found coverage elsewhere.",
        "Cancel everything. Policy {pid}, all of it. Rate hikes, runaround on my claim, lack of communication. I'm switching to {comp}.",
    ],
}
T_GENERAL = {
    "positive": [
        "Hi, calling to update my address. Everything's been great with my coverage. The claim I had last year was handled beautifully.",
        "Hello, I need to add a new vehicle. By the way, your claims team did an excellent job last time. Very smooth process.",
        "I'm calling about bundling my policies. I have auto and I'm interested in home coverage. Very happy with the service so far.",
    ],
    "neutral": [
        "Hi, I need to update vehicle information on my auto policy. I recently purchased a new car and want the right coverage.",
        "Hello, calling to ask about my coverage limits. I want to make sure I have adequate protection. Can someone review my policy?",
        "I'd like information about adding umbrella coverage to my existing policies. What are my options?",
    ],
}

TONE_SENTIMENT = {
    "positive":    ("POSITIVE", (0.80, 0.95)),
    "neutral":     ("NEUTRAL",  (0.45, 0.55)),
    "concerned":   ("NEUTRAL",  (0.35, 0.45)),
    "frustrated":  ("NEGATIVE", (0.18, 0.32)),
    "angry":       ("NEGATIVE", (0.08, 0.18)),
    "threatening": ("NEGATIVE", (0.02, 0.10)),
}

def sentiment_from_tone(tone):
    label, (lo, hi) = TONE_SENTIMENT.get(tone, ("NEUTRAL", (0.45, 0.55)))
    return label, round(random.uniform(lo, hi), 4)

def pick_transcript(templates, tone, **kw):
    pool = templates.get(tone, list(templates.values())[0])
    t = random.choice(pool)
    try:
        return t.format(**kw)
    except (KeyError, IndexError):
        return t


# ═══════════════════════════════════════════════════════════════════
# GENERATORS
# ═══════════════════════════════════════════════════════════════════

def gen_households():
    rows = []
    for i in range(1, NUM_HOUSEHOLDS + 1):
        rows.append({
            "HOUSEHOLD_ID": fid("HH", i),
            "ADDRESS": raddr(),
            "STATE": random.choice(STATES),
            "POSTAL_CODE": rzip(),
            "MEMBER_COUNT": 0,
        })
    return rows


def gen_parties(households):
    parties = []
    # Build assignment: each HH gets at least 1 member
    assign = list(range(NUM_HOUSEHOLDS))
    # Remaining 190 go to random HHs (but NOT HH-00001, index 0)
    for _ in range(NUM_PARTIES - NUM_HOUSEHOLDS):
        assign.append(random.randint(1, NUM_HOUSEHOLDS - 1))
    random.shuffle(assign)

    # Force CUST-00001 → HH-00001 (idx 0), CUST-00002 → HH-00001 (idx 0)
    # Remove any existing references to idx 0 and place them at positions 0,1
    assign = [a for a in assign if a != 0]
    # Trim to 498, then prepend two 0s
    assign = assign[:NUM_PARTIES - 2]
    assign = [0, 0] + assign

    # Count members per HH
    counts = defaultdict(int)
    for a in assign:
        counts[a] += 1
    for idx, c in counts.items():
        households[idx]["MEMBER_COUNT"] = c

    for i in range(NUM_PARTIES):
        hh = households[assign[i]]
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        tenure = random.choices(
            [random.uniform(0.2, 1), random.uniform(1, 3), random.uniform(3, 8), random.uniform(8, 20)],
            weights=[15, 25, 35, 25],
        )[0]
        created = TODAY - timedelta(days=int(tenure * 365))
        parties.append({
            "PARTY_ID": fid("CUST", i + 1),
            "FIRST_NAME": first,
            "LAST_NAME": last,
            "DATE_OF_BIRTH": date(random.randint(1955, 2005), random.randint(1, 12), random.randint(1, 28)),
            "EMAIL": remail(first, last),
            "PHONE": rphone(),
            "MAILING_ADDRESS": hh["ADDRESS"],
            "STATE": hh["STATE"],
            "POSTAL_CODE": hh["POSTAL_CODE"],
            "CREATED_AT": datetime(created.year, created.month, created.day, 9, 0, 0),
            "HOUSEHOLD_ID": hh["HOUSEHOLD_ID"],
        })
    return parties


def gen_policies(parties):
    policies = []
    prem_hist = {}  # pol_id → {old, new, pct}
    n = 1
    for party in parties:
        pid = party["PARTY_ID"]
        lobs = []
        if random.random() < 0.70: lobs.append("AUTO")
        if random.random() < 0.40: lobs.append("HOME")
        if random.random() < 0.10: lobs.append("UMBRELLA")
        if random.random() < 0.15 and "HOME" not in lobs: lobs.append("RENTERS")
        if not lobs: lobs.append("AUTO")

        tenure_days = (TODAY - party["CREATED_AT"].date()).days
        for lob in lobs:
            plo, phi = PREMIUM_RANGES[lob]
            dlo, dhi = DEDUCTIBLE_RANGES[lob]
            clo, chi = COVERAGE_RANGES[lob]
            premium = round(random.uniform(plo, phi), 2)

            roll = random.random()
            if roll < 0.65:   status = "ACTIVE"
            elif roll < 0.80: status = "PENDING_RENEWAL"
            elif roll < 0.90: status = "EXPIRED"
            else:             status = "CANCELLED"

            renewal_count = max(0, int(tenure_days / 365) - 1)
            if renewal_count > 0:
                eff = TODAY - timedelta(days=random.randint(30, 330))
            else:
                eff = party["CREATED_AT"].date() + timedelta(days=random.randint(0, 60))
            exp = eff + timedelta(days=365)
            bind = eff - timedelta(days=random.randint(7, 30))
            cancel = None

            if status == "PENDING_RENEWAL":
                exp = TODAY + timedelta(days=random.randint(5, 60))
                eff = exp - timedelta(days=365)
                inc = random.choices(
                    [0, random.uniform(3, 8), random.uniform(8, 15), random.uniform(15, 30)],
                    weights=[40, 30, 20, 10],
                )[0]
                if inc > 0:
                    old_p = premium / (1 + inc / 100)
                    prem_hist[fid("POL", n)] = {"old": round(old_p, 2), "new": premium, "pct": inc}

            if status == "CANCELLED":
                cancel = rdate(eff, min(exp, TODAY))

            policies.append({
                "POLICY_ID": fid("POL", n),
                "PARTY_ID": pid,
                "LINE_OF_BUSINESS": lob,
                "STATUS": status,
                "EFFECTIVE_DATE": eff,
                "EXPIRATION_DATE": exp,
                "PREMIUM_AMOUNT": premium,
                "DEDUCTIBLE": round(random.uniform(dlo, dhi), 2) if dhi > 0 else 0,
                "COVERAGE_LIMIT": round(random.uniform(clo, chi), 2),
                "BIND_DATE": bind,
                "CANCELLATION_DATE": cancel,
                "RENEWAL_COUNT": renewal_count,
            })
            n += 1
    return policies, prem_hist


def gen_claims(policies):
    claims = []
    n = 1
    eligible = [p for p in policies if p["STATUS"] in ("ACTIVE", "PENDING_RENEWAL", "EXPIRED")]
    sample = random.sample(eligible, k=int(len(eligible) * 0.25))
    for pol in sample:
        for _ in range(random.choices([1, 2, 3], weights=[70, 25, 5])[0]):
            loss = rdate(pol["EFFECTIVE_DATE"], min(pol["EXPIRATION_DATE"], TODAY))
            report = loss + timedelta(days=random.randint(0, 5))
            roll = random.random()
            if roll < 0.55:   st = "CLOSED"
            elif roll < 0.80: st = "OPEN"
            elif roll < 0.90: st = "DENIED"
            else:             st = "REOPENED"

            lob = pol["LINE_OF_BUSINESS"]
            ct = random.choice(["COLLISION", "LIABILITY", "THEFT"] if lob == "AUTO"
                               else ["PROPERTY_DAMAGE", "WEATHER", "THEFT", "LIABILITY"] if lob == "HOME"
                               else ["LIABILITY", "PROPERTY_DAMAGE"])
            reserve = round(random.uniform(1000, 150000), 2)
            paid = (round(reserve * random.uniform(0.3, 1.0), 2) if st == "CLOSED"
                    else 0 if st == "DENIED"
                    else round(reserve * random.uniform(0, 0.3), 2))

            claims.append({
                "CLAIM_ID": fid("CLM", n),
                "POLICY_ID": pol["POLICY_ID"],
                "PARTY_ID": pol["PARTY_ID"],
                "LOSS_DATE": loss,
                "REPORT_DATE": report,
                "CLAIM_STATUS": st,
                "CLAIM_TYPE": ct,
                "RESERVE_AMOUNT": reserve,
                "PAID_AMOUNT": paid,
                "FAULT_INDICATOR": random.choice(["AT_FAULT", "NOT_AT_FAULT", "PARTIAL"]),
            })
            n += 1
    return claims


def gen_billing(policies):
    rows = []
    n = 1
    for pol in policies:
        end = (pol["CANCELLATION_DATE"] if pol["STATUS"] == "CANCELLED" and pol["CANCELLATION_DATE"]
               else min(pol["EXPIRATION_DATE"], TODAY))
        num = random.randint(2, 6)
        amt = round(pol["PREMIUM_AMOUNT"] / num, 2)
        for j in range(num):
            due = pol["EFFECTIVE_DATE"] + timedelta(days=int(365 * j / num))
            if due > end:
                break
            if due < TODAY - timedelta(days=30):
                r = random.random()
                if r < 0.85:   bst, pd, ap = "PAID", due + timedelta(days=random.randint(0, 15)), amt
                elif r < 0.93: bst, pd, ap = "PAST_DUE", None, 0
                elif r < 0.97: bst, pd, ap = "GRACE", None, 0
                else:          bst, pd, ap = "COLLECTIONS", None, 0
            else:
                if random.random() < 0.6:
                    bst, pd, ap = "PAID", due - timedelta(days=random.randint(0, 5)), amt
                else:
                    bst, pd, ap = "GRACE", None, 0
            rows.append({
                "BILLING_ID": fid("BIL", n),
                "POLICY_ID": pol["POLICY_ID"],
                "PARTY_ID": pol["PARTY_ID"],
                "DUE_DATE": due,
                "AMOUNT_DUE": amt,
                "AMOUNT_PAID": ap,
                "PAYMENT_DATE": pd,
                "PAYMENT_METHOD": random.choice(["ACH", "CARD", "CHECK", "ONLINE"]) if ap > 0 else None,
                "BILLING_STATUS": bst,
            })
            n += 1
    return rows


def gen_quotes(parties, policies):
    rows = []
    n = 1
    pp = defaultdict(list)
    for p in policies:
        pp[p["PARTY_ID"]].append(p)
    for party in parties:
        pid = party["PARTY_ID"]
        pols = pp.get(pid, [])
        if random.random() < 0.20 and pols:
            ref = random.choice(pols)
            rows.append({
                "QUOTE_ID": fid("QUO", n),
                "PARTY_ID": pid,
                "LINE_OF_BUSINESS": ref["LINE_OF_BUSINESS"],
                "QUOTED_PREMIUM": round(ref["PREMIUM_AMOUNT"] * random.uniform(0.70, 0.95), 2),
                "QUOTE_DATE": rdate(TODAY - timedelta(days=60), TODAY),
                "QUOTE_STATUS": random.choice(["QUOTED", "EXPIRED", "DECLINED"]),
                "SOURCE": random.choice(["WEB", "AGENT", "PARTNER"]),
            })
            n += 1
        if random.random() < 0.10:
            lob = random.choice(list(PREMIUM_RANGES.keys()))
            lo, hi = PREMIUM_RANGES[lob]
            rows.append({
                "QUOTE_ID": fid("QUO", n),
                "PARTY_ID": pid,
                "LINE_OF_BUSINESS": lob,
                "QUOTED_PREMIUM": round(random.uniform(lo, hi), 2),
                "QUOTE_DATE": rdate(TODAY - timedelta(days=90), TODAY),
                "QUOTE_STATUS": random.choice(["QUOTED", "BOUND", "EXPIRED", "DECLINED"]),
                "SOURCE": random.choice(["WEB", "AGENT", "PARTNER"]),
            })
            n += 1
    # Anonymous quotes
    for _ in range(30):
        lob = random.choice(list(PREMIUM_RANGES.keys()))
        lo, hi = PREMIUM_RANGES[lob]
        rows.append({
            "QUOTE_ID": fid("QUO", n), "PARTY_ID": None,
            "LINE_OF_BUSINESS": lob,
            "QUOTED_PREMIUM": round(random.uniform(lo, hi), 2),
            "QUOTE_DATE": rdate(TODAY - timedelta(days=90), TODAY),
            "QUOTE_STATUS": "QUOTED", "SOURCE": "WEB",
        })
        n += 1
    return rows


# ═══════════════════════════════════════════════════════════════════
# SITUATION ANALYSIS → drives transcript tone
# ═══════════════════════════════════════════════════════════════════

def compute_situations(parties, policies, claims, billing, prem_hist):
    pp = defaultdict(list)
    pc = defaultdict(list)
    pb = defaultdict(list)
    for p in policies: pp[p["PARTY_ID"]].append(p)
    for c in claims:   pc[c["PARTY_ID"]].append(c)
    for b in billing:  pb[b["PARTY_ID"]].append(b)

    sits = {}
    for party in parties:
        pid = party["PARTY_ID"]
        pols = pp[pid]
        cls = pc[pid]
        tenure = (TODAY - party["CREATED_AT"].date()).days / 365.0

        # Premium shock
        shock_pol = shock_pct = None
        for pol in pols:
            ph = prem_hist.get(pol["POLICY_ID"])
            if ph and ph["pct"] > 10:
                shock_pol, shock_pct = pol, ph["pct"]
                break

        # Worst open claim
        open_cls = [c for c in cls if c["CLAIM_STATUS"] in ("OPEN", "REOPENED")]
        worst = None
        worst_days = 0
        for c in open_cls:
            d = (TODAY - c["REPORT_DATE"]).days
            if d > worst_days:
                worst, worst_days = c, d

        denied = [c for c in cls if c["CLAIM_STATUS"] == "DENIED"]
        past_due = [b for b in pb[pid] if b["BILLING_STATUS"] in ("PAST_DUE", "COLLECTIONS")]

        sits[pid] = {
            "tenure": tenure, "policies": pols,
            "shock_pol": shock_pol, "shock_pct": shock_pct,
            "worst_claim": worst, "claim_days": worst_days,
            "claim_frustrated": worst_days > 30,
            "denied": denied, "past_due": past_due,
        }
    return sits


# ═══════════════════════════════════════════════════════════════════
# INTERACTION GENERATOR — causal transcript linking
# ═══════════════════════════════════════════════════════════════════

def gen_interactions(parties, sits, policies, prem_hist):
    rows = []
    n = 1

    pp = defaultdict(list)
    for p in policies:
        pp[p["PARTY_ID"]].append(p)

    for party in parties:
        pid = party["PARTY_ID"]
        sit = sits[pid]
        pols = pp.get(pid, [])
        if not pols:
            continue
        calls = []

        # ── Premium-shock calls (2-3, escalating) ──
        if sit["shock_pol"]:
            pol = sit["shock_pol"]
            ph = prem_hist[pol["POLICY_ID"]]
            comp = random.choice(COMPETITORS)
            comp_prem = round(ph["new"] * random.uniform(0.65, 0.85), 2)
            tones = ["concerned", "frustrated"]
            if sit["shock_pct"] > 18:
                tones.append(random.choice(["angry", "threatening"]))
            kw = dict(pid=pol["POLICY_ID"], lob=pol["LINE_OF_BUSINESS"].lower(),
                      old=ph["old"], new=ph["new"], pct=ph["pct"],
                      delta=ph["new"] - ph["old"], tenure=int(sit["tenure"]),
                      comp=comp, comp_prem=comp_prem, savings=ph["new"] - comp_prem)
            for j, tone in enumerate(tones):
                days_ago = 5 + (len(tones) - j - 1) * random.randint(6, 10)
                txt = pick_transcript(T_PREMIUM if tone != "threatening" else
                                      (T_CANCEL if random.random() < 0.3 else T_PREMIUM), tone, **kw)
                sent, score = sentiment_from_tone(tone)
                topic = "PREMIUM_INQUIRY" if tone == "concerned" else "COMPLAINT" if tone in ("frustrated", "angry") else "CANCELLATION_REQUEST"
                resol = "FOLLOW_UP" if tone == "concerned" else "ESCALATED" if tone in ("frustrated", "angry") else "UNRESOLVED"
                calls.append(dict(days=days_ago, topic=topic, txt=txt, sent=sent, score=score,
                                  resol=resol, dur=random.randint(180, 600), rpol=pol["POLICY_ID"], rclm=None))

        # ── Claim-frustrated calls (2-3, escalating) ──
        if sit["claim_frustrated"] and sit["worst_claim"]:
            c = sit["worst_claim"]
            days_open = sit["claim_days"]
            tones = (["concerned", "frustrated", "angry"] if days_open > 50
                     else ["concerned", "frustrated"])
            kw = dict(cid=c["CLAIM_ID"], days=days_open,
                      ctype=c["CLAIM_TYPE"].lower().replace("_", " "))
            for j, tone in enumerate(tones):
                days_ago = 3 + (len(tones) - j - 1) * random.randint(5, 9)
                txt = pick_transcript(T_CLAIM, tone, **kw)
                sent, score = sentiment_from_tone(tone)
                resol = "FOLLOW_UP" if j < len(tones) - 1 else random.choice(["ESCALATED", "UNRESOLVED"])
                calls.append(dict(days=days_ago, topic="CLAIM_STATUS", txt=txt, sent=sent, score=score,
                                  resol=resol, dur=random.randint(120, 480), rpol=None, rclm=c["CLAIM_ID"]))

        # ── Denied-claim call ──
        if sit["denied"]:
            dc = sit["denied"][0]
            tone = random.choice(["angry", "frustrated"])
            kw = dict(cid=dc["CLAIM_ID"], days=(TODAY - dc["REPORT_DATE"]).days,
                      ctype=dc["CLAIM_TYPE"].lower().replace("_", " "))
            txt = pick_transcript(T_CLAIM, tone, **kw)
            sent, score = sentiment_from_tone(tone)
            calls.append(dict(days=random.randint(5, 30), topic="CLAIM_STATUS", txt=txt, sent=sent,
                              score=score, resol="ESCALATED", dur=random.randint(180, 420),
                              rpol=None, rclm=dc["CLAIM_ID"]))

        # ── Billing-issue call ──
        if sit["past_due"]:
            b = sit["past_due"][0]
            tone = random.choice(["concerned", "frustrated"])
            kw = dict(pid=b["POLICY_ID"], amt=b["AMOUNT_DUE"])
            txt = pick_transcript(T_BILLING, tone, **kw)
            sent, score = sentiment_from_tone(tone)
            calls.append(dict(days=random.randint(3, 25), topic="BILLING_INQUIRY", txt=txt, sent=sent,
                              score=score, resol=random.choice(["RESOLVED", "FOLLOW_UP"]),
                              dur=random.randint(120, 300), rpol=b["POLICY_ID"], rclm=None))

        # ── General / happy call (55% of those without issues, 30% extra for those with) ──
        if not calls and random.random() < 0.65:
            tone = random.choice(["positive", "neutral"])
            txt = pick_transcript(T_GENERAL, tone)
            sent, score = sentiment_from_tone(tone)
            topic = random.choice(["GENERAL_INQUIRY", "POLICY_CHANGE", "ADDRESS_CHANGE", "COVERAGE_QUESTION"])
            calls.append(dict(days=random.randint(1, 90), topic=topic, txt=txt, sent=sent, score=score,
                              resol="RESOLVED", dur=random.randint(60, 240),
                              rpol=random.choice(pols)["POLICY_ID"], rclm=None))
        elif calls and random.random() < 0.30:
            tone = random.choice(["positive", "neutral"])
            txt = pick_transcript(T_GENERAL, tone)
            sent, score = sentiment_from_tone(tone)
            topic = random.choice(["GENERAL_INQUIRY", "POLICY_CHANGE", "ADDRESS_CHANGE", "COVERAGE_QUESTION"])
            calls.append(dict(days=random.randint(30, 120), topic=topic, txt=txt, sent=sent, score=score,
                              resol="RESOLVED", dur=random.randint(60, 240),
                              rpol=random.choice(pols)["POLICY_ID"], rclm=None))

        # ── Emit phone interactions ──
        for call in calls:
            dt = NOW - timedelta(days=call["days"], hours=random.randint(0, 8))
            summ = (call["txt"][:150].rsplit(" ", 1)[0] + "...") if len(call["txt"]) > 150 else call["txt"]
            rows.append({
                "INTERACTION_ID": fid("INT", n, 6), "PARTY_ID": pid,
                "CHANNEL": "PHONE", "DIRECTION": "INBOUND",
                "INTERACTION_DATE": dt, "DURATION_SECONDS": call["dur"],
                "TOPIC": call["topic"], "TRANSCRIPT_TEXT": call["txt"],
                "SUMMARY": summ, "SENTIMENT": call["sent"],
                "SENTIMENT_SCORE": call["score"], "RESOLUTION": call["resol"],
                "RELATED_POLICY_ID": call["rpol"], "RELATED_CLAIM_ID": call["rclm"],
            })
            n += 1

        # ── Web interactions (0-3) ──
        web_topics = ["ACCOUNT_LOGIN", "POLICY_VIEW", "CLAIM_VIEW", "BILLING_VIEW",
                      "RATE_COMPARISON", "CANCELLATION_PAGE", "COVERAGE_REVIEW", "FAQ"]
        wt_weights = ([5, 10, 10, 5, 25, 20, 15, 10] if (sit["shock_pol"] or sit["claim_frustrated"])
                      else [15, 15, 10, 10, 10, 5, 20, 15])
        for _ in range(random.choices([0, 1, 2, 3], weights=[40, 30, 20, 10])[0]):
            wdt = NOW - timedelta(days=random.randint(1, 60), hours=random.randint(0, 14))
            wt = random.choices(web_topics, weights=wt_weights)[0]
            rows.append({
                "INTERACTION_ID": fid("INT", n, 6), "PARTY_ID": pid,
                "CHANNEL": "WEB", "DIRECTION": "INBOUND",
                "INTERACTION_DATE": wdt, "DURATION_SECONDS": random.randint(30, 600),
                "TOPIC": wt, "TRANSCRIPT_TEXT": None,
                "SUMMARY": f"Web session: viewed {wt.lower().replace('_', ' ')} page",
                "SENTIMENT": None, "SENTIMENT_SCORE": None,
                "RESOLUTION": None, "RELATED_POLICY_ID": None, "RELATED_CLAIM_ID": None,
            })
            n += 1

        # ── Email (15% chance) ──
        if random.random() < 0.15:
            edt = NOW - timedelta(days=random.randint(1, 45))
            et = random.choice(["BILLING_INQUIRY", "POLICY_CHANGE", "GENERAL_INQUIRY"])
            rows.append({
                "INTERACTION_ID": fid("INT", n, 6), "PARTY_ID": pid,
                "CHANNEL": "EMAIL", "DIRECTION": "INBOUND",
                "INTERACTION_DATE": edt, "DURATION_SECONDS": None,
                "TOPIC": et, "TRANSCRIPT_TEXT": None,
                "SUMMARY": f"Email inquiry about {et.lower().replace('_', ' ')}",
                "SENTIMENT": random.choice(["NEUTRAL", "NEGATIVE"]),
                "SENTIMENT_SCORE": round(random.uniform(0.30, 0.55), 4),
                "RESOLUTION": random.choice(["RESOLVED", "FOLLOW_UP"]),
                "RELATED_POLICY_ID": random.choice(pols)["POLICY_ID"] if pols else None,
                "RELATED_CLAIM_ID": None,
            })
            n += 1

    return rows, n  # return next counter for hero injection


# ═══════════════════════════════════════════════════════════════════
# HERO CUSTOMER — CUST-00001
# ═══════════════════════════════════════════════════════════════════

def purge_and_inject_hero(households, parties, policies, claims, billing,
                          interactions, quotes, prem_hist, next_int):
    hero_ids = {"CUST-00001", "CUST-00002"}

    # ── Purge all random data for hero IDs ──
    hero_pols = {p["POLICY_ID"] for p in policies if p["PARTY_ID"] in hero_ids}
    policies[:]     = [p for p in policies     if p["PARTY_ID"] not in hero_ids]
    claims[:]       = [c for c in claims       if c["PARTY_ID"] not in hero_ids]
    billing[:]      = [b for b in billing      if b["PARTY_ID"] not in hero_ids]
    interactions[:] = [i for i in interactions  if i["PARTY_ID"] not in hero_ids]
    quotes[:]       = [q for q in quotes       if q.get("PARTY_ID") not in hero_ids]
    for pid in list(prem_hist.keys()):
        if pid in hero_pols:
            del prem_hist[pid]

    # ── Fix household HH-00001 ──
    hh = next(h for h in households if h["HOUSEHOLD_ID"] == "HH-00001")
    hh["ADDRESS"] = "742 Evergreen Terrace"
    hh["STATE"] = "CA"
    hh["POSTAL_CODE"] = "94105"
    hh["MEMBER_COUNT"] = 2

    # ── Fix CUST-00001 (hero) ──
    hero = next(p for p in parties if p["PARTY_ID"] == "CUST-00001")
    hero.update({
        "FIRST_NAME": "Arjun", "LAST_NAME": "Mehta",
        "DATE_OF_BIRTH": date(1978, 3, 14),
        "EMAIL": "arjun.mehta@gmail.com", "PHONE": "(415) 555-0101",
        "MAILING_ADDRESS": "742 Evergreen Terrace",
        "STATE": "CA", "POSTAL_CODE": "94105",
        "CREATED_AT": datetime(2013, 7, 15, 9, 0, 0),
        "HOUSEHOLD_ID": "HH-00001",
    })

    # ── Fix CUST-00002 (household member, auto only) ──
    member = next(p for p in parties if p["PARTY_ID"] == "CUST-00002")
    member.update({
        "FIRST_NAME": "Priya", "LAST_NAME": "Mehta",
        "DATE_OF_BIRTH": date(1980, 11, 22),
        "EMAIL": "priya.mehta@gmail.com", "PHONE": "(415) 555-0102",
        "MAILING_ADDRESS": "742 Evergreen Terrace",
        "STATE": "CA", "POSTAL_CODE": "94105",
        "CREATED_AT": datetime(2015, 3, 10, 9, 0, 0),
        "HOUSEHOLD_ID": "HH-00001",
    })

    # ── New IDs (continue from max existing) ──
    mx = lambda lst, key: max((int(r[key].split("-")[1]) for r in lst), default=0)
    np_ = mx(policies, "POLICY_ID") + 1
    nc  = mx(claims,   "CLAIM_ID")  + 1
    nb  = mx(billing,  "BILLING_ID") + 1
    nq  = mx(quotes,   "QUOTE_ID")  + 1
    ni  = next_int

    # ── Hero auto policy — renewing in 23 days, 27.5% increase ──
    hero_pol = fid("POL", np_)
    old_prem, new_prem = 36000.00, 45900.00
    policies.append({
        "POLICY_ID": hero_pol, "PARTY_ID": "CUST-00001",
        "LINE_OF_BUSINESS": "AUTO", "STATUS": "PENDING_RENEWAL",
        "EFFECTIVE_DATE": date(2024, 8, 7),
        "EXPIRATION_DATE": TODAY + timedelta(days=23),
        "PREMIUM_AMOUNT": new_prem, "DEDUCTIBLE": 2500.00,
        "COVERAGE_LIMIT": 300000.00, "BIND_DATE": date(2024, 7, 25),
        "CANCELLATION_DATE": None, "RENEWAL_COUNT": 11,
    })
    prem_hist[hero_pol] = {"old": old_prem, "new": new_prem, "pct": 27.5}

    # ── CUST-00002 auto policy (active, clean) ──
    mem_pol = fid("POL", np_ + 1)
    policies.append({
        "POLICY_ID": mem_pol, "PARTY_ID": "CUST-00002",
        "LINE_OF_BUSINESS": "AUTO", "STATUS": "ACTIVE",
        "EFFECTIVE_DATE": date(2025, 1, 15),
        "EXPIRATION_DATE": date(2026, 1, 15),
        "PREMIUM_AMOUNT": 22000.00, "DEDUCTIBLE": 2000.00,
        "COVERAGE_LIMIT": 200000.00, "BIND_DATE": date(2025, 1, 5),
        "CANCELLATION_DATE": None, "RENEWAL_COUNT": 9,
    })

    # ── Hero claim — disputed liability, open 74 days, not at fault ──
    hero_clm = fid("CLM", nc)
    loss = TODAY - timedelta(days=74)
    claims.append({
        "CLAIM_ID": hero_clm, "POLICY_ID": hero_pol, "PARTY_ID": "CUST-00001",
        "LOSS_DATE": loss, "REPORT_DATE": loss + timedelta(days=1),
        "CLAIM_STATUS": "OPEN", "CLAIM_TYPE": "LIABILITY",
        "RESERVE_AMOUNT": 85000.00, "PAID_AMOUNT": 0.00,
        "FAULT_INDICATOR": "NOT_AT_FAULT",
    })

    # ── Hero billing (quarterly, 2 paid + 1 grace) ──
    for j, (dback, st, paid) in enumerate([
        (180, "PAID", True), (90, "PAID", True), (30, "GRACE", False),
    ]):
        billing.append({
            "BILLING_ID": fid("BIL", nb + j), "POLICY_ID": hero_pol,
            "PARTY_ID": "CUST-00001",
            "DUE_DATE": TODAY - timedelta(days=dback),
            "AMOUNT_DUE": 11475.00,
            "AMOUNT_PAID": 11475.00 if paid else 0,
            "PAYMENT_DATE": (TODAY - timedelta(days=dback - 3)) if paid else None,
            "PAYMENT_METHOD": "ACH" if paid else None,
            "BILLING_STATUS": st,
        })
    # Member billing
    billing.append({
        "BILLING_ID": fid("BIL", nb + 3), "POLICY_ID": mem_pol,
        "PARTY_ID": "CUST-00002",
        "DUE_DATE": TODAY - timedelta(days=15), "AMOUNT_DUE": 5500.00,
        "AMOUNT_PAID": 5500.00,
        "PAYMENT_DATE": TODAY - timedelta(days=12),
        "PAYMENT_METHOD": "CARD", "BILLING_STATUS": "PAID",
    })

    # ── Hero's 3 calls — spread across time so trajectory signal fires ──
    # Call 1 at 68 days ago (prior 30–60d window): reasonable / concerned
    # Call 2 at 41 days ago (prior 30–60d window): frustrated
    # Call 3 at 9 days ago  (recent 0–30d window): angry, names competitor
    # Trajectory: prior avg ~0.28  vs recent 0.04 → decline > 0.10 → fires
    hero_calls = [
        {
            "days": 68, "topic": "PREMIUM_INQUIRY",
            "txt": (
                f"Hello, I'm calling about my auto policy {hero_pol}. I just received my renewal notice "
                f"and I see the premium is going up from 36,000 to 45,900 — that's a 27.5 percent increase. "
                f"I've been insured with you for 12 years and I've maintained a clean driving record. Can you "
                f"help me understand why my rate is increasing so much? I'd like to discuss my options."
            ),
            "sent": "NEUTRAL", "score": 0.3800, "resol": "FOLLOW_UP", "dur": 420,
        },
        {
            "days": 41, "topic": "COMPLAINT",
            "txt": (
                f"This is Arjun Mehta, policy {hero_pol}. I called almost a month ago about my premium "
                f"increase and was told someone would get back to me. No one did. Meanwhile, I also have an "
                f"open claim {hero_clm} that's been sitting for weeks with no resolution — I wasn't even at "
                f"fault! So you're raising my rates by 27 percent while failing to settle a legitimate claim. "
                f"I'm extremely frustrated and I need answers today."
            ),
            "sent": "NEGATIVE", "score": 0.1800, "resol": "ESCALATED", "dur": 540,
        },
        {
            "days": 9, "topic": "CANCELLATION_REQUEST",
            "txt": (
                f"This is my third call. Policy {hero_pol}, claim {hero_clm}. Nothing has changed. "
                f"My premium is still 45,900, my claim is still unresolved after 74 days, and nobody from your "
                f"company seems to care. I've been a loyal customer for 12 years, paying on time every single "
                f"quarter. I've already gotten a quote from Kavach General for 32,900 — that's 13,000 less "
                f"than what you're charging me. If I don't hear back with a real resolution by end of this week, "
                f"I'm switching. I'm done being taken for granted."
            ),
            "sent": "NEGATIVE", "score": 0.0400, "resol": "UNRESOLVED", "dur": 660,
        },
    ]
    for j, c in enumerate(hero_calls):
        dt = NOW - timedelta(days=c["days"], hours=random.randint(1, 4))
        summ = c["txt"][:150].rsplit(" ", 1)[0] + "..."
        interactions.append({
            "INTERACTION_ID": fid("INT", ni + j, 6), "PARTY_ID": "CUST-00001",
            "CHANNEL": "PHONE", "DIRECTION": "INBOUND",
            "INTERACTION_DATE": dt, "DURATION_SECONDS": c["dur"],
            "TOPIC": c["topic"], "TRANSCRIPT_TEXT": c["txt"],
            "SUMMARY": summ, "SENTIMENT": c["sent"],
            "SENTIMENT_SCORE": c["score"], "RESOLUTION": c["resol"],
            "RELATED_POLICY_ID": hero_pol,
            "RELATED_CLAIM_ID": hero_clm if "claim" in c["txt"].lower() else None,
        })
    ni += len(hero_calls)

    # ── Hero web interactions (4 page views spanning both time windows) ──
    for j, (dago, wt) in enumerate([
        (50, "RATE_COMPARISON"), (35, "CANCELLATION_PAGE"),
        (12, "RATE_COMPARISON"), (5, "CANCELLATION_PAGE"),
    ]):
        wdt = NOW - timedelta(days=dago, hours=random.randint(6, 12))
        interactions.append({
            "INTERACTION_ID": fid("INT", ni + j, 6), "PARTY_ID": "CUST-00001",
            "CHANNEL": "WEB", "DIRECTION": "INBOUND",
            "INTERACTION_DATE": wdt, "DURATION_SECONDS": random.randint(120, 480),
            "TOPIC": wt, "TRANSCRIPT_TEXT": None,
            "SUMMARY": f"Web session: viewed {wt.lower().replace('_', ' ')} page",
            "SENTIMENT": None, "SENTIMENT_SCORE": None,
            "RESOLUTION": None, "RELATED_POLICY_ID": None, "RELATED_CLAIM_ID": None,
        })
    ni += 4

    # ── Hero competitor quote — 13,000 cheaper ──
    quotes.append({
        "QUOTE_ID": fid("QUO", nq), "PARTY_ID": "CUST-00001",
        "LINE_OF_BUSINESS": "AUTO",
        "QUOTED_PREMIUM": 32900.00,
        "QUOTE_DATE": TODAY - timedelta(days=8),
        "QUOTE_STATUS": "QUOTED", "SOURCE": "WEB",
    })


# ═══════════════════════════════════════════════════════════════════
# CSV WRITER
# ═══════════════════════════════════════════════════════════════════

FIELDS = {
    "household":   ["HOUSEHOLD_ID", "ADDRESS", "STATE", "POSTAL_CODE", "MEMBER_COUNT"],
    "party":       ["PARTY_ID", "FIRST_NAME", "LAST_NAME", "DATE_OF_BIRTH", "EMAIL", "PHONE",
                    "MAILING_ADDRESS", "STATE", "POSTAL_CODE", "CREATED_AT", "HOUSEHOLD_ID"],
    "policy":      ["POLICY_ID", "PARTY_ID", "LINE_OF_BUSINESS", "STATUS", "EFFECTIVE_DATE",
                    "EXPIRATION_DATE", "PREMIUM_AMOUNT", "DEDUCTIBLE", "COVERAGE_LIMIT",
                    "BIND_DATE", "CANCELLATION_DATE", "RENEWAL_COUNT"],
    "claim":       ["CLAIM_ID", "POLICY_ID", "PARTY_ID", "LOSS_DATE", "REPORT_DATE",
                    "CLAIM_STATUS", "CLAIM_TYPE", "RESERVE_AMOUNT", "PAID_AMOUNT", "FAULT_INDICATOR"],
    "billing":     ["BILLING_ID", "POLICY_ID", "PARTY_ID", "DUE_DATE", "AMOUNT_DUE",
                    "AMOUNT_PAID", "PAYMENT_DATE", "PAYMENT_METHOD", "BILLING_STATUS"],
    "interaction": ["INTERACTION_ID", "PARTY_ID", "CHANNEL", "DIRECTION", "INTERACTION_DATE",
                    "DURATION_SECONDS", "TOPIC", "TRANSCRIPT_TEXT", "SUMMARY", "SENTIMENT",
                    "SENTIMENT_SCORE", "RESOLUTION", "RELATED_POLICY_ID", "RELATED_CLAIM_ID"],
    "quote":       ["QUOTE_ID", "PARTY_ID", "LINE_OF_BUSINESS", "QUOTED_PREMIUM", "QUOTE_DATE",
                    "QUOTE_STATUS", "SOURCE"],
}

def write_csv(name, data):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    fields = FIELDS[name]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in data:
            w.writerow({k: fval(row.get(k)) for k in fields})
    print(f"  {name}.csv: {len(data):,} rows")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    random.seed(SEED)
    print("Meridian 360 — Synthetic Data Generator")
    print("=" * 50)

    print("\n1. Generating households...")
    households = gen_households()

    print("2. Generating parties...")
    parties = gen_parties(households)

    print("3. Generating policies...")
    policies, prem_hist = gen_policies(parties)

    print("4. Generating claims...")
    claims = gen_claims(policies)

    print("5. Generating billing...")
    billing = gen_billing(policies)

    print("6. Generating quotes...")
    quotes = gen_quotes(parties, policies)

    print("7. Computing customer situations...")
    sits = compute_situations(parties, policies, claims, billing, prem_hist)

    print("8. Generating interactions (causal transcripts)...")
    interactions, next_int = gen_interactions(parties, sits, policies, prem_hist)

    print("9. Purging CUST-00001/00002 and injecting hero storyline...")
    purge_and_inject_hero(households, parties, policies, claims, billing,
                          interactions, quotes, prem_hist, next_int)

    print("\n10. Writing CSVs...")
    write_csv("household", households)
    write_csv("party", parties)
    write_csv("policy", policies)
    write_csv("claim", claims)
    write_csv("billing", billing)
    write_csv("interaction", interactions)
    write_csv("quote", quotes)

    phone = sum(1 for i in interactions if i["CHANNEL"] == "PHONE")
    web = sum(1 for i in interactions if i["CHANNEL"] == "WEB")
    email = sum(1 for i in interactions if i["CHANNEL"] == "EMAIL")

    print(f"\n{'─'*50}")
    print(f"Households:    {len(households):,}")
    print(f"Parties:       {len(parties):,}")
    print(f"Policies:      {len(policies):,}")
    print(f"Claims:        {len(claims):,}")
    print(f"Billing:       {len(billing):,}")
    print(f"Interactions:  {len(interactions):,}  (phone={phone}, web={web}, email={email})")
    print(f"Quotes:        {len(quotes):,}")
    print(f"\nCSVs written to: {DATA_DIR}")


if __name__ == "__main__":
    main()
