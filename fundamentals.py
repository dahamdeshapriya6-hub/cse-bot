"""Step 6: company facts for every share -> data/fundamentals.json,
plus company announcements, financial reports and upcoming dividends -> data/announcements.json
 1. Asks the CSE feed for each company's summary (market value, foreign holding, etc.).
    Refreshed once a week per share, so daily runs stay fast.
 2. Optional: reads data/manual_fundamentals.csv  (symbol,eps,navps,dps)
    and works out PER, PBV and dividend yield from the current price.
 3. First run only: tries a few other CSE endpoints and saves what they return to
    data/probe_fundamentals.json, so we can see what else is available."""
import csv, json, os, time, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

BASE = "https://www.cse.lk/api/"
D = "data"
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Origin": "https://www.cse.lk", "Referer": "https://www.cse.lk/"}


def call(endpoint, params=None, get=False):
    body = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(BASE + endpoint, data=None if get else body,
                                 method="GET" if get else "POST", headers=HEAD)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def num(x):
    try: return float(str(x).replace(",", ""))
    except Exception: return None


def probe(sym):
    out = {}
    tries = [("companyInfoSummery", {"symbol": sym}, False), ("smd/categories", None, True),
             ("approvedAnnouncement", {}, False), ("getFinancialAnnouncement", {}, False),
             ("getNewAnnouncement", {}, False), ("circularAnnouncement", {}, False),
             ("financialAnnouncement", {}, False), ("companyInfoVideo", {"symbol": sym}, False)]
    for ep, p, g in tries:
        try:
            txt = json.dumps(call(ep, p, g))
            out[ep] = {"length": len(txt), "start": txt[:600]}
        except Exception as e:
            out[ep] = {"error": str(e)[:80]}
    with open(f"{D}/probe_fundamentals.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("Probe saved to data/probe_fundamentals.json")


def pdate(s):
    for f in ("%d %b %Y", "%d/%b/%Y", "%d-%b-%Y", "%Y-%m-%d", "%d %b %Y %I:%M:%S %p"):
        try: return datetime.strptime(str(s).strip().title(), f).date()
        except Exception: pass
    return None


def announcements(syms, names):
    """Company announcements and financial reports from the CSE feed -> data/announcements.json"""
    path = f"{D}/announcements_store.json"
    try: store = json.load(open(path, encoding="utf-8"))
    except Exception: store = {}
    ap, fin = store.get("approved", {}), store.get("financial", {})
    try:
        for a in call("approvedAnnouncement", {}).get("approvedAnnouncements", []):
            ap[str(a["id"])] = {k: a.get(k) for k in ("createdDate", "dateOfAnnouncement", "announcementCategory", "company",
                                "symbol", "recordDate", "xd", "xr", "paymentDate", "agmDate", "remarks", "type") if a.get(k)}
    except Exception as e: print("approvedAnnouncement failed:", str(e)[:80])
    try:
        for a in call("getFinancialAnnouncement", {}).get("reqFinancialAnnouncemnets", []):
            fin[str(a["id"])] = {k: a.get(k) for k in ("path", "uploadedDate", "fileText", "name", "symbol") if a.get(k)}
    except Exception as e: print("getFinancialAnnouncement failed:", str(e)[:80])
    cut = (datetime.now(timezone.utc) - timedelta(days=120))
    ap = {k: v for k, v in ap.items() if (v.get("createdDate") or 1e18) / 1000 >= cut.timestamp()}
    fin = {k: v for k, v in fin.items() if (pdate(v.get("uploadedDate")) or date.today()) >= cut.date()}
    store = {"approved": ap, "financial": fin}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))

    prefix, byname = defaultdict(list), defaultdict(list)
    for sym in syms:
        prefix[sym.split(".")[0]].append(sym)
        byname[names.get(sym, "").upper().strip()].append(sym)
    by = defaultdict(lambda: {"ann": [], "reports": []})
    today, upcoming = date.today(), []
    for a in sorted(ap.values(), key=lambda a: -(a.get("createdDate") or 0)):
        tgt = byname.get(str(a.get("company", "")).upper().strip()) or prefix.get(str(a.get("symbol", "")).split(".")[0], [])
        for sym in tgt:
            if len(by[sym]["ann"]) < 6: by[sym]["ann"].append(a)
        cat = str(a.get("announcementCategory", "")).upper()
        if any(w in cat for w in ("DIVIDEND", "RIGHTS", "CAPITALI", "SPLIT", "SUBDIVISION")):
            ds = [pdate(a.get(k)) for k in ("xd", "xr", "recordDate", "paymentDate")]
            ds = [d for d in ds if d and d >= today]
            if ds: upcoming.append((min(ds), {**a, "symbols": tgt}))
    for a in sorted(fin.values(), key=lambda a: pdate(a.get("uploadedDate")) or date.min, reverse=True):
        for sym in prefix.get(str(a.get("symbol", "")).split(".")[0], []):
            if len(by[sym]["reports"]) < 3:
                by[sym]["reports"].append({"title": a.get("fileText"), "date": a.get("uploadedDate", "")[:11],
                                           "link": "https://cdn.cse.lk/" + a.get("path", "")})
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "upcoming": [u for _, u in sorted(upcoming, key=lambda t: t[0])][:25], "byShare": by}
    with open(f"{D}/announcements.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Announcements: {len(ap)} kept, {len(fin)} financial reports, {len(upcoming)} upcoming dividend/rights events, "
          f"{len(by)} shares with notices")


def main():
    path = f"{D}/fundamentals.json"
    old = {}
    if os.path.exists(path):
        try: old = json.load(open(path, encoding="utf-8")).get("shares", {})
        except Exception: old = {}
    with open(f"{D}/shares.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    syms = [r["symbol"] for r in rows]
    names = {r["symbol"]: r["name"] for r in rows}
    last = {}
    try:
        last = {s["symbol"]: s["last"] for s in json.load(open(f"{D}/results.json"))["shares"]}
    except Exception: pass
    manual = {}
    if os.path.exists(f"{D}/manual_fundamentals.csv"):
        with open(f"{D}/manual_fundamentals.csv", newline="", encoding="utf-8") as f:
            manual = {r["symbol"].strip(): r for r in csv.DictReader(f)}

    week = (date.today() - timedelta(days=7)).isoformat()
    shares, got, failed = {}, 0, 0
    for sym in syms:
        rec = old.get(sym, {})
        if rec.get("info") and rec.get("v") == 2 and rec.get("fetched", "") >= week:
            shares[sym] = rec; continue
        try:
            pl = call("companyInfoSummery", {"symbol": sym}) or {}
            info = pl.get("reqSymbolInfo") or {}
            rec = {"info": {k: v for k, v in info.items() if v is not None}, "beta": pl.get("reqSymbolBetaInfo"),
                   "fetched": date.today().isoformat(), "v": 2}
            got += 1
        except Exception:
            failed += 1
            rec = rec or {"info": {}, "fetched": ""}
        shares[sym] = rec
        time.sleep(0.25)

    for sym, rec in shares.items():
        m = manual.get(sym)
        px = last.get(sym)
        if m and px:
            eps, nav, dps = num(m.get("eps")), num(m.get("navps")), num(m.get("dps"))
            rec["manual"] = {"eps": eps, "navps": nav, "dps": dps,
                             "per": round(px / eps, 1) if eps and eps > 0 else None,
                             "pbv": round(px / nav, 2) if nav and nav > 0 else None,
                             "yield": round(100 * dps / px, 1) if dps is not None else None}
        else:
            rec.pop("manual", None)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "shares": shares},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"Company facts: {got} refreshed, {failed} failed, {len(shares) - got - failed} reused; "
          f"manual figures for {sum(1 for r in shares.values() if 'manual' in r)} shares")
    try:
        announcements(syms, names)
    except Exception as e:
        print("Announcements skipped:", str(e)[:100])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Fundamentals step skipped:", e)
