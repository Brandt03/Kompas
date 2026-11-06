#!/usr/bin/env python3
"""Månedens gennemgang (Økonomi): the numbers for the routine Kompas · Økonomi and the page Gennemgang.

  gennemgang.py rapport [--maaned YYYY-MM] [--gem]   one whole month's numbers as JSON (default: last month);
                                                     --gem also keeps them as ../gennemgang/<maaned>.tal.json
  gennemgang.py byg                                  collects ../gennemgang/ into public/gennemgang/gennemgange.json

Reads only public/data.json (Sure's export, every 5 min), so it works while Sure is stopped. Every number the routine
writes comes from here; it adds nothing up itself. Spending is counted like Forbrug: everything outside Indtægter and
Opsparing og investering, net of refunds per category, by calendar month like Sure's budgets. Income too, except SU:
it is paid on the last banking day for the month after, so an SU payment in a month's last week counts for the next.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HER = Path(__file__).resolve().parent
DATA = HER / "public" / "data.json"
GEMT = HER.parent / "gennemgang"  # the routine's reviews: <maaned>.md, <maaned>.json and the numbers <maaned>.tal.json
UD = HER / "public" / "gennemgang" / "gennemgange.json"

INCOME, SAVINGS, FIXED = "Indtægter", "Opsparing og investering", "Faste udgifter"
SU = "SU"
BIG = 500          # store_udgifter: single payments of at least this much outside Faste udgifter
SUGGEST_MIN = 50   # budget suggestion when the 3-month average is this far from the budget ...
SUGGEST_PCT = 0.2  # ... and this share of it, outside Faste udgifter, and used in 0, 2 or 3 of the 3 months


def ym(d):
    return d[:7]


def add_months(key, n):
    y, m = map(int, key.split("-"))
    m += n
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def last_day(key):
    return date.fromisoformat(add_months(key, 1) + "-01") - timedelta(days=1)


def income_month(t):
    """The month an income counts for: SU in a month's last 7 days belongs to the next month."""
    d = date.fromisoformat(t["date"])
    if t["category"] == SU and d > last_day(ym(t["date"])) - timedelta(days=7):
        return add_months(ym(t["date"]), 1)
    return ym(t["date"])


def is_spend(t):
    return t["group"] not in (INCOME, SAVINGS) and (t["category"] is not None or t["amount"] > 0)


def r2(x):
    return None if x is None else round(x, 2)


def spend_by_category(tx, key):
    """Net spending per category in one month; categories that net to 0 or less drop out, like on Forbrug."""
    net = defaultdict(float)
    for t in tx:
        if t["ym"] == key and is_spend(t):
            net[(t["category"] or "Ukategoriseret", t["group"] or "Ukategoriseret")] += t["amount"]
    return {k: v for k, v in net.items() if v > 0.005}


def rapport(d, key):
    tx = [{**t, "amount": float(t["amount"]), "ym": ym(t["date"])} for t in d["transactions"]]
    first = min((t["ym"] for t in tx), default=key)
    months3 = [m for m in (add_months(key, -2), add_months(key, -1), key) if m >= first]
    before3 = [m for m in (add_months(key, -3), add_months(key, -2), add_months(key, -1)) if m >= first]
    per_month = {m: spend_by_category(tx, m) for m in {*months3, *before3, add_months(key, -1)}}
    now = spend_by_category(tx, key)
    total = lambda m: sum(per_month[m].values()) if m in per_month else sum(spend_by_category(tx, m).values())

    budgets = {b["month"]: b for b in d.get("budgets", [])}
    own = defaultdict(dict)  # month -> category -> its own budget
    for b in d.get("budget_categories", []):
        own[b["month"]][b["category"]] = float(b["budget"]) if b["budget"] is not None else None

    # categories: everything with spending this month or a budget above 0, groups themselves listed under grupper
    groups_of = {b["category"]: b["group"] for b in d.get("budget_categories", [])}
    names = {c for c, _ in now} | {c for c, b in own.get(key, {}).items() if b and groups_of.get(c) != c}
    group_names = {c: g for (c, g) in now} | {c: groups_of[c] for c in names if c in groups_of}
    kategorier = []
    for c in sorted(names):
        g = group_names.get(c)
        if c == g:
            continue
        brugt = sum(v for (cc, _), v in now.items() if cc == c)
        spent = [sum(v for (cc, _), v in per_month[m].items() if cc == c) for m in months3]
        avg = sum(spent) / len(months3)
        months_used = sum(1 for v in spent if v > 0)
        budget = own.get(key, {}).get(c)
        suggest = None
        # one big payment in one month (a trip, a winter coat) is no reason to change the monthly budget, and fixed
        # expenses follow their bills (a rent that started mid-period would otherwise be "suggested" down)
        if (budget is not None and g != FIXED and months_used != 1
                and abs(avg - budget) >= max(SUGGEST_MIN, SUGGEST_PCT * budget)):
            suggest = round(avg / 25) * 25
        kategorier.append({
            "kategori": c, "gruppe": g, "brugt": r2(brugt), "budget": budget,
            "afvigelse": r2(brugt - budget) if budget is not None else None,
            "forrige_maaned": r2(sum(v for (cc, _), v in per_month[add_months(key, -1)].items() if cc == c)),
            "snit_3_mdr": r2(avg), "maaneder_med_forbrug": months_used, "forslag_budget": suggest,
            "naeste_budget": own.get(add_months(key, 1), {}).get(c),
        })
    kategorier.sort(key=lambda k: -(k["brugt"] or 0))

    grupper = []
    for g in sorted({g for (_, g) in now} | {c for c, gg in groups_of.items() if c == gg and own.get(key, {}).get(c)}):
        if g in (INCOME, SAVINGS):
            continue
        brugt = sum(v for (_, gg), v in now.items() if gg == g)
        budget = own.get(key, {}).get(g)
        grupper.append({"gruppe": g, "brugt": r2(brugt), "budget": budget,
                        "afvigelse": r2(brugt - budget) if budget is not None else None})
    grupper.sort(key=lambda x: -(x["brugt"] or 0))

    inc = defaultdict(float)
    for t in tx:
        if t["group"] == INCOME and income_month(t) == key:
            inc[t["category"] or INCOME] -= t["amount"]
    indtaegter = sorted(({"kategori": c, "beloeb": r2(v)} for c, v in inc.items() if abs(v) > 0.005), key=lambda x: -x["beloeb"])
    inc_total = sum(inc.values())
    spend_total = sum(now.values())
    budget_total = budgets.get(key, {}).get("spending")

    big = sorted((t for t in tx if t["ym"] == key and is_spend(t) and t["group"] != FIXED and t["amount"] >= BIG),
                 key=lambda t: -t["amount"])[:5]

    faste = (d.get("faste") or {}).get("betalinger", [])
    since = add_months(key, -2) + "-01"
    tags = defaultdict(float)
    for t in tx:
        if t["ym"] == key and is_spend(t):
            for tag in t.get("tags") or []:
                tags[tag] += t["amount"]
    uncat = [t for t in tx if t["ym"] == key and is_spend(t) and t["category"] is None]

    balances = {a["name"]: float(a["balance"]) for a in d.get("accounts", [])}
    maal = []
    for g in d.get("goals", []):
        saved = sum(balances.get(a, 0) for a in g.get("accounts", []))
        maal.append({"navn": g["name"], "maal": float(g["target"]), "konti": g.get("accounts", []),
                     "saldo_nu": r2(saved), "mangler": r2(max(float(g["target"]) - saved, 0)), "dato": g.get("target_date")})

    synced = d.get("last_sync")
    complete = bool(synced) and synced[:10] > last_day(key).isoformat()
    return {
        "maaned": key,
        "periode": {"fra": key + "-01", "til": last_day(key).isoformat()},
        "data": {
            "hentet": d.get("generated_at"), "bank_synkroniseret": synced, "hel_maaned": complete,
            "forbehold": None if complete else
                f"Sure har sidst synkroniseret med banken {(synced or 'aldrig')[:10]}, før måneden sluttede, så tallene er ufuldstændige.",
        },
        "forbrug": {
            "i_alt": r2(spend_total), "budget": budget_total,
            "afvigelse": r2(spend_total - budget_total) if budget_total is not None else None,
            "forrige_maaned": r2(total(add_months(key, -1))),
            "snit_3_mdr_foer": r2(sum(total(m) for m in before3) / len(before3)) if before3 else None,
        },
        "grupper": grupper,
        "kategorier": kategorier,
        "indtaegter": {"i_alt": r2(inc_total), "kategorier": indtaegter,
                       "budget": budgets.get(key, {}).get("income")},
        "netto": r2(inc_total - spend_total),
        "store_udgifter": [{"dato": t["date"], "navn": t["name"], "kategori": t["category"], "beloeb": r2(t["amount"]),
                            "tags": t.get("tags") or []} for t in big],
        "faste": {
            "pr_maaned": r2((d.get("faste") or {}).get("pr_maaned")),
            "aktive": [f for f in faste if f["aktiv"]],
            "nye": [f for f in faste if f["foerste"] and ym(f["foerste"]) == key],
            "prisaendringer": [f for f in faste if f["foer"] is not None and ym(f["sidst"]) == key],
            "ikke_betalt_siden": [f for f in faste if not f["aktiv"] and f["sidst"] >= since],
        },
        "tags": [{"tag": k, "brugt": r2(v)} for k, v in sorted(tags.items(), key=lambda x: -x[1])],
        "ukategoriseret": {"antal": len(uncat), "beloeb": r2(sum(t["amount"] for t in uncat))},
        "konti_nu": [{"navn": n, "saldo": r2(b)} for n, b in sorted(balances.items())],
        "maal": maal,
    }


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def byg():
    """Every review the routine has saved, newest first, with the numbers it was written from."""
    out = []
    for f in sorted(GEMT.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].json"), reverse=True):
        tal = f.with_name(f.stem + ".tal.json")
        try:
            out.append({"maaned": f.stem, "gennemgang": json.loads(f.read_text()),
                        "tal": json.loads(tal.read_text()) if tal.exists() else None})
        except (OSError, ValueError) as e:
            print(f"{f.name}: kunne ikke læses ({e}); springes over", file=sys.stderr)
    write_json(UD, {"bygget": datetime.now().isoformat(timespec="seconds"), "gennemgange": out})
    print(f"{len(out)} gennemgange → {UD}")


def main(argv):
    if argv[:1] == ["byg"]:
        return byg()
    if argv[:1] != ["rapport"]:
        sys.exit(__doc__)
    key = argv[argv.index("--maaned") + 1] if "--maaned" in argv else add_months(date.today().isoformat()[:7], -1)
    d = json.loads(DATA.read_text())
    tal = rapport(d, key)
    if "--gem" in argv:
        write_json(GEMT / f"{key}.tal.json", tal)
    print(json.dumps(tal, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
