"""Step 6: company facts for every share -> data/fundamentals.json
 1. Asks the CSE feed for each company's summary (market value, foreign holding, etc.).
    Refreshed once a week per share, so daily runs stay fast.
 2. Optional: reads data/manual_fundamentals.csv  (symbol,eps,navps,dps)
    and works out PER, PBV and dividend yield from the current price.
 3. First run only: tries a few other CSE endpoints and saves what they return to
    data/probe_fundamentals.json, so we can see what else is available."""
import csv, json, os, time, urllib.parse, urllib.request
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


def main():
    path = f"{D}/fundamentals.json"
    old = {}
    if os.path.exists(path):
        try: old = json.load(open(path, encoding="utf-8")).get("shares", {})
        except Exception: old = {}
    syms = []
    with open(f"{D}/shares.csv", newline="", encoding="utf-8") as f:
        syms = [r["symbol"] for r in csv.DictReader(f)]
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
        if rec.get("info") and rec.get("fetched", "") >= week:
            shares[sym] = rec; continue
        try:
            info = (call("companyInfoSummery", {"symbol": sym}) or {}).get("reqSymbolInfo") or {}
            rec = {"info": {k: v for k, v in info.items() if v is not None}, "fetched": date.today().isoformat()}
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
    if not os.path.exists(f"{D}/probe_fundamentals.json") and syms:
        probe(syms[0])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Fundamentals step skipped:", e)
