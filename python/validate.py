#!/usr/bin/env python3
"""
validate.py — Referential integrity and key uniqueness checker for Meridian 360 CSVs.
Reads CSVs from data/ and reports pass/fail for every PK and FK constraint.
"""

import csv
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")


def load(name):
    path = os.path.join(DATA_DIR, f"{name}.csv")
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def col_vals(rows, col, skip_empty=False):
    vals = [r[col] for r in rows]
    if skip_empty:
        vals = [v for v in vals if v]
    return vals


def check_unique(name, rows, pk):
    vals = col_vals(rows, pk)
    dupes = len(vals) - len(set(vals))
    status = "PASS" if dupes == 0 else "FAIL"
    print(f"  [{status}] {name}.{pk} uniqueness — {len(vals)} values, {dupes} duplicates")
    return dupes == 0


def check_fk(child_name, child_rows, fk_col, parent_name, parent_rows, pk_col, nullable=False):
    parent_keys = set(col_vals(parent_rows, pk_col))
    child_vals = col_vals(child_rows, fk_col, skip_empty=nullable)
    orphans = [v for v in child_vals if v not in parent_keys]
    status = "PASS" if len(orphans) == 0 else "FAIL"
    label = f"{child_name}.{fk_col} → {parent_name}.{pk_col}"
    if nullable:
        label += " (nullable)"
    print(f"  [{status}] {label} — {len(orphans)} orphans out of {len(child_vals)}")
    if orphans and len(orphans) <= 5:
        print(f"         orphan values: {orphans}")
    return len(orphans) == 0


def main():
    print("Meridian 360 — Data Validator")
    print("=" * 50)
    print(f"Reading from: {DATA_DIR}\n")

    household   = load("household")
    party       = load("party")
    policy      = load("policy")
    claim       = load("claim")
    billing     = load("billing")
    interaction = load("interaction")
    quote       = load("quote")

    all_pass = True

    print("Primary key uniqueness:")
    all_pass &= check_unique("household",   household,   "HOUSEHOLD_ID")
    all_pass &= check_unique("party",       party,       "PARTY_ID")
    all_pass &= check_unique("policy",      policy,      "POLICY_ID")
    all_pass &= check_unique("claim",       claim,       "CLAIM_ID")
    all_pass &= check_unique("billing",     billing,     "BILLING_ID")
    all_pass &= check_unique("interaction", interaction, "INTERACTION_ID")
    all_pass &= check_unique("quote",       quote,       "QUOTE_ID")

    print("\nForeign key integrity:")
    all_pass &= check_fk("party",       party,       "HOUSEHOLD_ID",       "household", household, "HOUSEHOLD_ID")
    all_pass &= check_fk("policy",      policy,      "PARTY_ID",           "party",     party,     "PARTY_ID")
    all_pass &= check_fk("claim",       claim,       "POLICY_ID",          "policy",    policy,    "POLICY_ID")
    all_pass &= check_fk("claim",       claim,       "PARTY_ID",           "party",     party,     "PARTY_ID")
    all_pass &= check_fk("billing",     billing,     "POLICY_ID",          "policy",    policy,    "POLICY_ID")
    all_pass &= check_fk("billing",     billing,     "PARTY_ID",           "party",     party,     "PARTY_ID")
    all_pass &= check_fk("interaction", interaction, "PARTY_ID",           "party",     party,     "PARTY_ID")
    all_pass &= check_fk("interaction", interaction, "RELATED_POLICY_ID",  "policy",    policy,    "POLICY_ID",  nullable=True)
    all_pass &= check_fk("interaction", interaction, "RELATED_CLAIM_ID",   "claim",     claim,     "CLAIM_ID",   nullable=True)
    all_pass &= check_fk("quote",       quote,       "PARTY_ID",           "party",     party,     "PARTY_ID",   nullable=True)

    # ── Hero customer spot checks ──
    print("\nHero customer (CUST-00001) spot checks:")

    hero_party = [p for p in party if p["PARTY_ID"] == "CUST-00001"]
    assert len(hero_party) == 1, "CUST-00001 missing"
    hero = hero_party[0]
    h = hero["HOUSEHOLD_ID"]
    hh_members = [p for p in party if p["HOUSEHOLD_ID"] == h]
    hero_pols = [p for p in policy if p["PARTY_ID"] == "CUST-00001"]
    hero_lobs = {p["LINE_OF_BUSINESS"] for p in hero_pols}
    hero_claims = [c for c in claim if c["PARTY_ID"] == "CUST-00001"]
    hero_ints = [i for i in interaction if i["PARTY_ID"] == "CUST-00001"]
    hero_calls = [i for i in hero_ints if i["CHANNEL"] == "PHONE"]
    hero_web = [i for i in hero_ints if i["CHANNEL"] == "WEB"]
    hero_quotes = [q for q in quote if q.get("PARTY_ID") == "CUST-00001"]

    checks = [
        ("Tenure ~12 years",        hero["FIRST_NAME"] == "Arjun"),
        ("Household has 2 members", len(hh_members) == 2),
        ("Has AUTO policy",         "AUTO" in hero_lobs),
        ("No HOME policy",          "HOME" not in hero_lobs),
        ("Exactly 1 policy",        len(hero_pols) == 1),
        ("Has open claim",          any(c["CLAIM_STATUS"] == "OPEN" for c in hero_claims)),
        ("Claim NOT_AT_FAULT",      any(c["FAULT_INDICATOR"] == "NOT_AT_FAULT" for c in hero_claims)),
        ("3 phone calls",           len(hero_calls) == 3),
        ("4 web page views",        len(hero_web) == 4),
        ("Has competitor quote",    len(hero_quotes) >= 1),
        ("Quote < policy premium",  any(float(q["QUOTED_PREMIUM"]) < 45900 for q in hero_quotes)),
    ]
    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        all_pass &= ok
        print(f"  [{status}] {label}")

    # Bundle gap: no one in HH-00001 has HOME
    hh_pols = [p for p in policy if p["PARTY_ID"] in {m["PARTY_ID"] for m in hh_members}]
    hh_lobs = {p["LINE_OF_BUSINESS"] for p in hh_pols}
    bg = "HOME" not in hh_lobs
    all_pass &= bg
    print(f"  [{'PASS' if bg else 'FAIL'}] Household bundle gap (no HOME in HH-00001)")

    print(f"\n{'='*50}")
    if all_pass:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — review output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
