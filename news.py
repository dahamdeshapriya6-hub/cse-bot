"""Step 5: collects business-news headlines and links them to shares.
Writes data/news.json. Only headlines and links are stored, never article text.
To add a news source, add its RSS address to FEEDS below."""
import csv, json, re, time, urllib.parse, urllib.request
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
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def parse(raw, source):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:          # some feeds have extra text after the feed: keep only the feed itself
        cut = raw.split(b"</rss>")[0] + b"</rss>" if b"</rss>" in raw else raw
        root = ET.fromstring(cut)
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


def gnews(query, source=None):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query + " when:14d")
           + "&hl=en-LK&gl=LK&ceid=LK:en")
    got = parse(fetch(url), "Google News")
    for x in got:                  # titles look like "Headline - Newspaper"
        if " - " in x["title"]:
            x["title"], x["source"] = x["title"].rsplit(" - ", 1)
    return got


def about(title, nm, tick):
    """Is this headline really about the company?"""
    text = " " + norm(title) + " "
    w = nm.split()
    two = " ".join(w[:2])
    return (nm and f" {nm} " in text) or (len(w) > 1 and not set(w[:2]) <= GENERIC and f" {two} " in text) \
        or (len(tick) >= 3 and re.search(rf"\b{re.escape(tick)}\b", title) is not None)


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
    # Google News searches: market-wide topics, then the most traded companies
    gm, gc, gstat = [], {}, {"source": "Google News", "ok": True, "items": 0}
    try:
        for q in ["Colombo Stock Exchange", "CSE ASPI stocks", "Sri Lanka economy", "Sri Lanka rupee interest rates",
                  "Central Bank of Sri Lanka"]:
            gm += gnews(q); time.sleep(1)
        raw_names = {}
        with open(f"{D}/shares.csv", newline="", encoding="utf-8") as f:
            raw_names = {r["symbol"]: r["name"] for r in csv.DictReader(f)}
        top = sorted((s for s in json.load(open(f"{D}/results.json"))["shares"] if not s["lowActivity"]),
                     key=lambda s: -s["turnover"])[:40]
        for s in top:
            nm0 = re.sub(r"\b(PLC|LTD|LIMITED)\b", "", raw_names.get(s["symbol"], s["symbol"]), flags=re.I).strip()
            nm = norm(nm0)
            try:
                hits = [x for x in gnews(f'"{nm0}" Sri Lanka') if about(x["title"], nm, s["symbol"].split(".")[0])]
            except Exception:
                hits = []
            gc[s["symbol"]] = hits; time.sleep(1)
        gstat["items"] = len(gm) + sum(len(v) for v in gc.values())
        print(f"Google News: {len(gm)} market headlines, company news for {sum(1 for v in gc.values() if v)} of {len(gc)} top shares")
    except Exception as e:
        gstat.update(ok=False, error=str(e)[:80]); print("Google News: failed (" + str(e)[:80] + ")")
    status.append(gstat)
    items += gm + [x for v in gc.values() for x in v]
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
        if any(x["link"] == g["link"] for g in gm):
            market.append(x)
        for sym, hs in gc.items():
            if any(x["link"] == g["link"] for g in hs):
                by.setdefault(sym, []).append(x)
        for sym, nm in names.items():
            tick = sym.split(".")[0]
            words = nm.split()
            short = " ".join(words[:2]) if len(words) > 2 and words[0] not in GENERIC else ""
            if x in by.get(sym, []):
                continue
            if (nm and f" {nm} " in text) or (len(tick) >= 3 and re.search(rf"\b{re.escape(tick)}\b", x["title"])) \
                    or (len(short) >= 9 and f" {short} " in text):
                by.setdefault(sym, []).append(x); hit = True
        if any(w in low for w in MARKET_WORDS) and x not in market:
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
