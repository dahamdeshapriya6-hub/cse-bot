"""Step 4: tests simple ideas on liquid shares and prints a scoreboard.
Question for each idea: did the shares it picked beat the average share
over the next 5 and 20 trading days?"""
import csv, math
from collections import defaultdict
from analyze import adjust, num

D = "data"


def load():
    rows = defaultdict(list)
    with open(f"{D}/prices.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["symbol"]].append((r["date"], num(r["close"]), num(r["volume"])))
    dates = sorted({d for v in rows.values() for d, _, _ in v})
    ix = {d: i for i, d in enumerate(dates)}
    px, vol = {}, {}
    for s, v in rows.items():
        v.sort()
        adj, _ = adjust([x[1] for x in v])
        p, q = [None] * len(dates), [0.0] * len(dates)
        for (d, c, qq), a in zip(v, adj):
            p[ix[d]] = a; q[ix[d]] = qq
        last = None
        for i in range(len(dates)):          # carry the last price forward
            if p[i] is None: p[i] = last
            else: last = p[i]
        px[s], vol[s] = p, q
    return dates, px, vol


def main():
    dates, px, vol = load()
    n = len(dates)
    H = (5, 20)
    edges = defaultdict(lambda: {h: [] for h in H})   # rule -> h -> [(day, edge)]
    for t in range(60, n - 20):
        feats = {}
        for s in px:
            p = px[s]
            if p[t] is None or p[t - 60] is None:
                continue
            v20 = vol[s][t - 19:t + 1]
            if sum(x > 0 for x in v20) < 15 or sum(x * (p[t] or 0) for x in v20) / 20 < 1e6:
                continue                      # keep only shares you can really trade
            lr = [math.log(p[i] / p[i - 1]) for i in range(t - 19, t + 1) if p[i] and p[i - 1]]
            feats[s] = {"mom60": p[t] / p[t - 60] - 1, "mom20": p[t] / p[t - 20] - 1,
                        "ret5": p[t] / p[t - 5] - 1,
                        "near": p[t] / max(x for x in p[:t + 1] if x),
                        "surge": vol[s][t] > 3 * (sum(v20) / 20) and p[t] > p[t - 1],
                        "vol": math.sqrt(sum(x * x for x in lr) / max(1, len(lr)))}
        if len(feats) < 15:
            continue
        k = max(3, len(feats) // 5)
        top = lambda key: sorted(feats, key=lambda s: -feats[s][key])[:k]
        bot = lambda key: sorted(feats, key=lambda s: feats[s][key])[:k]
        groups = {"Strong 60-day rise (momentum)": top("mom60"),
                  "Strong 20-day rise (momentum)": top("mom20"),
                  "Fell most in last 5 days (bounce?)": bot("ret5"),
                  "Fell most in last 20 days (bounce?)": bot("mom20"),
                  "Near its 1-year high": [s for s in feats if feats[s]["near"] >= .95],
                  "Volume surge on a rising day": [s for s in feats if feats[s]["surge"]],
                  "Calm shares (small daily swings)": bot("vol")}
        for h in H:
            fw = {s: px[s][t + h] / px[s][t] - 1 for s in feats if px[s][t + h]}
            if len(fw) < 15:
                continue
            mkt = sum(fw.values()) / len(fw)
            for name, g in groups.items():
                g = [s for s in g if s in fw]
                if len(g) >= 3:
                    edges[name][h].append((t, 100 * (sum(fw[s] for s in g) / len(g) - mkt)))

    print("Scoreboard (liquid shares only). 'Edge' = how much better the picked shares did")
    print("than the average share, in % points. 'WORKS' needs a clear edge, positive in BOTH halves\nof the year, and certainty of 3 or more (so luck is unlikely).\n")
    mid = (60 + n - 20) // 2
    for name, byh in edges.items():
        for h in H:
            e = byh[h]
            if len(e) < 30:
                continue
            avg = sum(x for _, x in e) / len(e)
            a = [x for t, x in e if t < mid]; b = [x for t, x in e if t >= mid]
            m1 = sum(a) / max(1, len(a)); m2 = sum(b) / max(1, len(b))
            beat = round(100 * sum(x > 0 for _, x in e) / len(e))
            # test on non-overlapping periods only, so luck is not counted twice
            z = [x for i, (_, x) in enumerate(e) if i % h == 0]
            sd = math.sqrt(sum((x - sum(z) / len(z)) ** 2 for x in z) / max(1, len(z) - 1))
            tstat = (sum(z) / len(z)) / (sd / math.sqrt(len(z))) if sd > 0 else 0
            ok = avg >= (.2 if h == 5 else .5) and m1 > 0 and m2 > 0 and beat >= 55 and tstat >= 3
            print(f"{name:38s} {h:2d}d  edge {avg:+.2f}%  beat market {beat}% of days  "
                  f"1st half {m1:+.2f}  2nd half {m2:+.2f}  certainty {tstat:.1f}  -> {'WORKS' if ok else 'no'}")


if __name__ == "__main__":
    main()
