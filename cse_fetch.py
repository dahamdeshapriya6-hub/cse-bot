"""
CSE price collector - Step 1 of the CSE analysis bot.

What it does each time you run it:
  1. Downloads today's share prices for all companies from cse.lk
  2. Saves the raw answer in  data/raw_YYYY-MM-DD.json
  3. Adds the rows to  data/history.csv  (one row per share per day)

Run it once a day after the market closes (2:30pm Sri Lanka time).
Needs only Python 3.8+ - nothing to install.
Note: this uses CSE's unofficial public feed, which can change without notice.
"""
import csv, json, os, sys, urllib.request, urllib.parse
from datetime import date

BASE = "https://www.cse.lk/api/"
DATA = "data"
HISTORY = os.path.join(DATA, "history.csv")


def call(endpoint, params=None):
    body = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(
        BASE + endpoint, data=body, method="POST",
        headers={"User-Agent": "Mozilla/5.0 (personal research script)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def rows_from(payload):
    """The feed answers with a list, or a dict that contains a list."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def main():
    os.makedirs(DATA, exist_ok=True)
    today = date.today().isoformat()

    try:
        payload = call("todaySharePrice")
    except Exception as e:
        print("Could not download prices:", e)
        print("Check your internet connection, then try again.")
        sys.exit(1)

    with open(os.path.join(DATA, f"raw_{today}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    rows = rows_from(payload)
    if not rows:
        print("The feed answered, but the format was not what I expected.")
        print("First 600 characters of the answer (send this to Claude):")
        print(json.dumps(payload)[:600])
        sys.exit(1)

    # keep every column the feed gives us, plus the date
    new = [{"date": today, **{k: r.get(k) for k in r}} for r in rows]
    cols = list(new[0].keys())

    old = []
    if os.path.exists(HISTORY):
        with open(HISTORY, newline="", encoding="utf-8") as f:
            old = [r for r in csv.DictReader(f) if r.get("date") != today]
        for r in old:
            for c in r:
                if c not in cols:
                    cols.append(c)

    with open(HISTORY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(old + new)

    print(f"Saved {len(new)} shares for {today}.")
    print(f"History file: {HISTORY}  ({len(old) + len(new)} rows in total)")
    print("\nSample of the first 2 shares:")
    for r in new[:2]:
        print(r)


if __name__ == "__main__":
    main()
