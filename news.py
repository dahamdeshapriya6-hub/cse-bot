"""Step 5: collects business-news headlines and links them to shares.
Writes data/news.json. Only headlines and links are stored, never article text.
To add a news source, add its RSS address to FEEDS below."""
import csv, json, re, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

D = "data"
FEEDS = [("EconomyNext", "https://economynext.com/feed/"),
         ("Daily FT", "https://www.ft.lk/rss/sectors/20"),
         ("Daily News", "https://www.dailynews.lk/feed/"),
         ("Daily Mirror", "https://www.dailymirror.lk/rss/business/395")]
MARKET_WORDS = ["cse", "colombo stock exchange", "aspi", "s&p sl20", "stock market", "share market",
                "bourse", "stocks close", "stocks end", "turnover", "rupee", "treasury bill", "central bank",
                "interest rate", "inflation", "imf"]
TAGS = [("Dividend", ["dividend"]), ("Results", ["profit", "earnings", "quarter", "results", "revenue"]),
        ("Rights / split", ["rights issue", "share split", "subdivision", "bonus issue", "capitalisation"]),
        ("Deal", ["acquire", "acquisition", "merger", "takeover", "stake"]),
        ("Warning", ["loss", "default", "suspend", "downgrade", "probe", "penalty", "fraud"])]
DROP = {"plc", "ltd", "limited", "pvt", "the", "co", "company"}
GENERIC = {"sri", "lanka", "ceylon", "the", "national", "first", "asia", "asian", "central", "united",
           "general", "royal", "new", "east", "west", "south", "north", "global", "international", "commercial"}


def norm(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("&", " and "))
    return " ".join(w for w in s.split() if w not in DROP)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal research script)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def parse(raw, source):
    root = ET.fromstring(raw)
    out = []
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        def g(tag):
            e = it.find(tag)
            if e is None: e = it.find("{http://www.w3.org/2005/Atom}" + tag)
            return (e.text or "").strip() if e is not None else ""
        link = g("link")
        if not link:
            e = it.find("{http://www.w3.org/2005/Atom}link")
            link = e.get("href", "") if e is not None else ""
        d = g("pubDate") or g("published") or g("updated")
        try: dt = parsedate_to_datetime(d)
        except Exception:
            try: dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except Exception: dt = None
        if dt is not None and dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        title = g("title")
        if title and link:
            out.append({"title": title, "link": link, "source": source,
                        "date": dt.date().isoformat() if dt else "", "_dt": dt})
    return out


def main():
    items, status = [], []
    for name, url in FEEDS:
        try:
            got = parse(fetch(url), name)
            items += got; status.append({"source": name, "ok": True, "items": len(got)})
            print(f"{name}: {len(got)} headlines")
        except Exception as e:
            status.append({"source": name, "ok": False, "error": str(e)[:80]})
            print(f"{name}: failed ({str(e)[:80]})")
    cutoff = datetime.now(timezone.utc) - timedelta(days=21)
    seen, fresh = set(), []
    for x in sorted(items, key=lambda x: x["_dt"] or cutoff, reverse=True):
        if x["link"] in seen or (x["_dt"] and x["_dt"] < cutoff): continue
        seen.add(x["link"]); fresh.append(x)

    names = {}
    try:
        with open(f"{D}/shares.csv", newline="", encoding="utf-8") as f:
            names = {r["symbol"]: norm(r["name"]) for r in csv.DictReader(f)}
    except Exception as e:
        print("No share list found:", e)

    market, by = [], {}
    for x in fresh:
        low, text = x["title"].lower(), " " + norm(x["title"]) + " "
        x["tags"] = [t for t, ws in TAGS if any(w in low for w in ws)]
        hit = False
        for sym, nm in names.items():
            tick = sym.split(".")[0]
            words = nm.split()
            short = " ".join(words[:2]) if len(words) > 2 and words[0] not in GENERIC else ""
            if (nm and f" {nm} " in text) or (len(tick) >= 3 and re.search(rf"\b{re.escape(tick)}\b", x["title"])) \
                    or (len(short) >= 9 and f" {short} " in text):
                by.setdefault(sym, []).append(x); hit = True
        if any(w in low for w in MARKET_WORDS):
            market.append(x)
    clean = lambda x: {k: x[k] for k in ("title", "link", "source", "date", "tags")}
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "feeds": status,
           "market": [clean(x) for x in market[:15]],
           "byShare": {s: [clean(x) for x in v[:5]] for s, v in by.items()}}
    with open(f"{D}/news.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved {len(fresh)} recent headlines: {len(out['market'])} market-wide, "
          f"{len(by)} shares with company news")


if __name__ == "__main__":
    main()
