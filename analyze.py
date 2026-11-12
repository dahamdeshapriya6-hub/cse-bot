"""Step 3: reads data/prices.csv + data/shares.csv, writes data/results.json
(trend signal, indicators and forecast ranges for every share)."""
import csv, json, math, os
from collections import defaultdict
from datetime import datetime, timezone

D = "data"


def adjust(c):
    """Undo share splits / consolidations (a sudden whole-number price jump)."""
    out, n = c[:], 0
    for i in range(len(c) - 1, 0, -1):
        if c[i - 1] <= 0 or c[i] <= 0:
            continue
        r = c[i - 1] / c[i]
        if any(abs(r - k) / k < .03 or abs(r * k - 1) < .03 for k in range(2, 11)):
            f = c[i] / c[i - 1]
            for j in range(i):
                out[j] *= f
            n += 1
    return out, n


def sma(a, n): return sum(a[-n:]) / n


def rsi(a, n=14):
    g = l = 0
    for i in range(len(a) - n, len(a)):
        d = a[i] - a[i - 1]
        g += max(d, 0); l += max(-d, 0)
    return 50 if g + l == 0 else 100 if l == 0 else 100 - 100 / (1 + g / l)


def sg(x, y, tol=0.0):
    return 1 if x > y * (1 + tol) else -1 if x < y * (1 - tol) else 0


def trend(a):
    if len(a) < 21:
        return 0, "Not enough data", []
    last, r = a[-1], rsi(a)
    pts = [(sg(last, sma(a, 20)), "price above 20-day average", "price below 20-day average"),
           (sg(sma(a, 5), sma(a, 20)), "5-day average above 20-day average", "5-day average below 20-day average"),
           (sg(last, a[-6]), "up over the last 5 days", "down over the last 5 days"),
           (1 if r > 52 else -1 if r < 48 else 0, "RSI above 50 (buyers stronger)", "RSI below 50 (sellers stronger)")]
    sc = sum(p[0] for p in pts)
    why = [p[1] if p[0] > 0 else p[2] for p in pts if p[0]]
    return sc, "Rising" if sc >= 2 else "Declining" if sc <= -2 else "Sideways", why


HS = (1, 5, 7, 14, 20, 30, 252)   # forecast horizons, in trading days
BT = (1, 5, 7, 14, 20, 30)        # horizons that can be tested on past data


def params(a):
    lr = [max(-.2, min(.2, math.log(a[i] / a[i - 1]))) for i in range(1, len(a)) if a[i - 1] > 0 and a[i] > 0]
    rec = lr[-20:]
    rms = lambda v: math.sqrt(sum(x * x for x in v) / max(1, len(v)))
    sig = max(.002, .5 * rms(lr[-120:]) + .5 * rms(rec))
    mu = max(-.003, min(.003, .15 * sum(rec) / max(1, len(rec))))
    return mu, sig


def band(last, mu, sig, h):
    m, s = mu * h, sig * math.sqrt(h)
    z = 1.2816 * s
    return (last * math.exp(m - z), last * math.exp(m), last * math.exp(m + z),
            50 * (1 + math.erf(m / (s * math.sqrt(2)))))


def forecast(a):
    mu, sig = params(a)
    out = {}
    for h in HS:
        lo, mid, hi, p = band(a[-1], mu, sig, h)
        out[str(h)] = [round(lo, 2), round(mid, 2), round(hi, 2), round(p)]
    return out


def accuracy(a):
    """Replay the forecast method on this share's own past.
    Per horizon: [direction right %, price inside range %, tests, share rose %]."""
    n = len(a)
    st = {h: [0, 0, 0, 0, 0] for h in BT}   # tests, dirRight, dirTotal, inRange, rose
    for t in range(60, n - 1):
        mu, sig = params(a[max(0, t - 120):t + 1])
        for h in BT:
            if t + h >= n:
                continue
            lo, mid, hi, p = band(a[t], mu, sig, h)
            s = st[h]; s[0] += 1
            s[3] += lo <= a[t + h] <= hi
            if a[t + h] != a[t]:
                s[2] += 1; s[4] += a[t + h] > a[t]
                s[1] += (p >= 50) == (a[t + h] > a[t])
    return {str(h): [round(100 * s[1] / s[2]), round(100 * s[3] / s[0]), s[0], round(100 * s[4] / s[2])]
            for h, s in st.items() if s[2] >= 30}


def num(x):
    try: return float(x)
    except Exception: return 0.0


def main():
    names = {}
    if os.path.exists(f"{D}/shares.csv"):
        with open(f"{D}/shares.csv", newline="", encoding="utf-8") as f:
            names = {r["symbol"]: r["name"] for r in csv.DictReader(f)}
    rows = defaultdict(list)
    with open(f"{D}/prices.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["symbol"]].append((r["date"], num(r["close"]), num(r["volume"])))
    dates = sorted({d for v in rows.values() for d, _, _ in v})
    recent = set(dates[-20:])
    stats = defaultdict(lambda: [0, 0.0, 0, 0])  # n, sum fwd, up, down
    res = []
    for sym, v in sorted(rows.items()):
        v.sort()
        raw = [x[1] for x in v]
        a, nsplit = adjust(raw)
        if len(a) < 21 or a[-1] <= 0:
            continue
        sc, label, why = trend(a)
        inactive = v[-1][0] < dates[-5]
        if inactive: label = "Inactive"
        ret = lambda n: round(100 * (a[-1] / a[-1 - n] - 1), 2) if len(a) > n else None
        last20 = [x for x in v if x[0] in recent]
        turn = sum(x[1] * x[2] for x in last20) / 20
        res.append({"symbol": sym, "name": names.get(sym, ""), "last": raw[-1], "date": v[-1][0],
                    **{f"ret{k}": ret(k) for k in (1, 5, 7, 14, 20, 30, 60)},
                    "sma5": round(sma(a, 5), 2), "sma20": round(sma(a, 20), 2),
                    "sma50": round(sma(a, 50), 2) if len(a) >= 50 else None, "rsi": round(rsi(a)),
                    "hi52": round(max(a), 2), "lo52": round(min(a), 2),
                    "turnover": round(turn), "daysTraded": len(last20), "lowActivity": turn < 500000 or len(last20) < 10,
                    "splitAdjusted": nsplit, "trend": label, "score": sc, "why": why,
                    "forecast": forecast(a) if not inactive else None,
                    "acc": accuracy(a) if not inactive else {},
                    "spark": [round(x, 2) for x in a[-60:]], "sparkDates": [x[0] for x in v[-60:]]})
        for t in range(25, len(a) - 5):
            lab = trend(a[:t + 1])[1]
            fwd = a[t + 5] / a[t] - 1
            s = stats[lab]; s[0] += 1; s[1] += fwd; s[2] += fwd > 0; s[3] += fwd < 0
            s = stats["All"]; s[0] += 1; s[1] += fwd; s[2] += fwd > 0; s[3] += fwd < 0
    bt = {k: {"n": s[0], "avgFwd5": round(100 * s[1] / s[0], 2),
              "pctUp": round(100 * s[2] / max(1, s[2] + s[3]))} for k, s in stats.items() if s[0]}
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "asOf": dates[-1], "backtest": bt, "shares": res}
    with open(f"{D}/results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    c = defaultdict(int)
    for r in res: c[r["trend"]] += 1
    print(f"Analysed {len(res)} shares as of {dates[-1]}: {dict(c)}")
    print("Backtest (what happened 5 days after each signal):", bt)


if __name__ == "__main__":
    main()
