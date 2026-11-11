"""
CSE price history - Step 2 of the CSE analysis bot.

Reads the share list from data/history.csv (made by cse_fetch.py), then asks
the CSE feed for about one year of DAILY prices for every share and saves
them in data/prices.csv with the columns:
    symbol, date, close, high, low, volume
Run cse_fetch.py first, then this script. Needs only Python 3.8+.
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.cse.lk/api/"
DATA = "data"
SL = timezone(timedelta(hours=5, minutes=30))   # Sri Lanka time


def call(endpoint, params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        BASE + endpoint, data=body, method="POST",
        headers={"User-Agent": "Mozilla/5.0 (personal research script)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def shares():
    seen = {}
    with open(os.path.join(DATA, "history.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("id") and r.get("symbol"):
                seen[r["id"]] = r["symbol"]
    return seen


def history(stock_id):
    for attempt in (1, 2):
        try:
            payload = call("companyChartDataByStock",
                           {"stockId": stock_id, "period": 5})
            pts = payload.get("chartData") or []
            out = {}
            for p in pts:
                if p.get("p") is None or not p.get("t"):
                    continue
                d = datetime.fromtimestamp(p["t"] / 1000, SL).date().isoformat()
                out[d] = (p["p"], p.get("h"), p.get("l"), p.get("q"))
            return out
        except Exception:
            time.sleep(1.5)
    return None


def main():
    if not os.path.exists(os.path.join(DATA, "history.csv")):
        print("data/history.csv not found - run cse_fetch.py first.")
        sys.exit(1)

    lst = shares()
    rows, failed = [], []
    for i, (sid, sym) in enumerate(lst.items(), 1):
        h = history(sid)
        if h is None:
            failed.append(sym)
        else:
            for d in sorted(h):
                c, hi, lo, q = h[d]
                rows.append([sym, d, c, hi, lo, q])
        if i % 50 == 0:
            print(f"  {i}/{len(lst)} shares done")
        time.sleep(0.2)

    if not rows:
        print("No price history came back. Send this message to Claude.")
        sys.exit(1)

    with open(os.path.join(DATA, "prices.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "date", "close", "high", "low", "volume"])
        w.writerows(rows)

    days = len({r[1] for r in rows})
    print(f"Saved {len(rows)} rows for {len(lst) - len(failed)} shares "
          f"({days} different days) in data/prices.csv")
    if failed:
        print(f"{len(failed)} shares had no data (often rarely traded): "
              + ", ".join(failed[:15]) + (" ..." if len(failed) > 15 else ""))


if __name__ == "__main__":
    main()
