"""BYOD tournament runner, open to any entrant.

This is the runnable, extensible harness behind the published
table: OUR shipped values are the built-in baseline, and any
number of bring-your-own entrants join via a manifest. Nothing third-party
ships here. You convert files you obtained yourself into the
normalized entrant format (make_entrants.py knows the common shops)
and the tournament grades everybody against everybody.

Protocol (identical to the paper's landscape): per-82 rates, skaters
with GP >= 30, strict common sample across ALL predictor and judge
columns, Spearman rank correlation vs each judge's next-season
values, mean over the three transitions 2022->23, 2023->24,
2024->25. Every entrant also enters as its own 5/4/3 Marcel
("<name>-marcel"). If a raw metric loses to a
regressed version of itself, the raw number is describing, not
predicting.

Entrant manifest (JSON; default data/entrants/entrants.json):

    {"entrants": [
        {"name": "EH", "csv": "data/entrants/eh.csv"},
        {"name": "MP", "csv": "data/entrants/mp.csv",
         "age_scale": 8.0}
    ]}

`age_scale` rescales the age-curve delta (derived in our WAR units)
into the entrant's units (e.g. MoneyPuck game score ~ 8x WAR
magnitude); default 1.0.

Normalized entrant CSV columns:
    player    display name (joins are normalized name + position)
    season    season START year as an integer (2022 = 2022-23)
    position  D or F (exclude goalies upstream)
    gp        games played
    value     the metric's season TOTAL in its own units

An entrant needs seasons 2022-2025 to enter (2025 = 2025-26, the
final judge year); earlier seasons, when present, feed its Marcel.
With no manifest (or an empty one) the tournament still runs:
ours vs ours-marcel judged by our own next-season values, the
out-of-the-box smoke test.

Usage:
    python harness/run_tournament.py [--manifest PATH]
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATA = REPO / "data"
SEASONS = ["season_2021_22", "season_2022_23", "season_2023_24",
           "season_2024_25"]
MIN_GP = 30
K = 40.0
YEARS = list(range(2019, 2026))          # marcel history window
TRANSITIONS = [2022, 2023, 2024]         # N -> N+1
REQUIRED_YEARS = {2022, 2023, 2024, 2025}


def _norm_name(s: str) -> str:
    """Join key: casefold, strip accents/punctuation/(D) suffixes."""
    s = s.replace("(D)", "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.casefold())


def _spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for rank, i in enumerate(order):
            r[i] = float(rank)
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


# ---------------------------------------------------------------------------
# Built-in baseline: our shipped values (identical machinery to the
# landscape of record: rates, age curve, and 5/4/3 + K projection).
# data/ours_values.csv and data/players.csv are flat exports of the
# same records the paper's script of record read.
# ---------------------------------------------------------------------------

pv = {s: {} for s in SEASONS}
pv["season_2025_26"] = {}
_season_of_year = {int(s[7:11]): s for s in SEASONS}
_season_of_year[2025] = "season_2025_26"
with open(DATA / "ours_values.csv", encoding="utf-8-sig",
          newline="") as _f:
    for _r in csv.DictReader(_f):
        _sname = _season_of_year[int(_r["season"])]
        pv[_sname][_r["pid"]] = {
            "position": _r["position"],
            "games_played": int(_r["gp"]),
            "WAR_indiv_component": float(_r["war_indiv"]),
        }
ch = {}
with open(DATA / "players.csv", encoding="utf-8-sig",
          newline="") as _f:
    for _r in csv.DictReader(_f):
        ch[int(_r["pid"])] = {
            "first_name": _r["first_name"],
            "last_name": _r["last_name"],
            "position": _r["position"],
            "birth_date": _r["birth_date"],
        }


def key_of(pid_s, rec):
    h = ch.get(int(pid_s)) or {}
    full = f"{h.get('first_name', '')} {h.get('last_name', '')}"
    return (_norm_name(full),
            "D" if rec.get("position") == "D" else "F")


def age_at(pid, year):
    bd = (ch.get(pid) or {}).get("birth_date")
    if not bd:
        return None
    y, m, d = (int(x) for x in bd.split("-"))
    return (date(year, 10, 1) - date(y, m, d)).days / 365.25


def rates(sname):
    out = {}
    for pid_s, rec in pv[sname].items():
        gp = rec.get("games_played") or 0
        if rec.get("position") == "G" or gp < MIN_GP:
            continue
        tot = (rec.get("WAR_indiv_component", 0) or 0)
        out[key_of(pid_s, rec)] = (tot / gp * 82, gp,
                                   "D" if rec.get("position") == "D"
                                   else "F", int(pid_s))
    return out


ours = {s: rates(s) for s in SEASONS}
ours["season_2025_26"] = rates("season_2025_26")

# age deltas from our base (population effect), smoothed +-1 year
_deltas = defaultdict(list)
for s1, s2 in zip(SEASONS, SEASONS[1:], strict=False):
    y2 = int(s2[7:11])
    for k, (v1_, g1, grp, pid) in ours[s1].items():
        nxt = ours[s2].get(k)
        if not nxt or g1 < 30 or nxt[1] < 30:
            continue
        a = age_at(pid, y2)
        if a is None:
            continue
        _deltas[(grp, round(a))].append((nxt[0] - v1_, min(g1, nxt[1])))
_ad = {kk: sum(d * g for d, g in v) / sum(g for _, g in v)
       for kk, v in _deltas.items()}
sm = {}
for _grp in ("F", "D"):
    for _a in range(19, 41):
        _vals = [_ad[(_grp, b)] for b in (_a - 1, _a, _a + 1)
                 if (_grp, b) in _ad]
        sm[(_grp, _a)] = sum(_vals) / len(_vals) if _vals else 0.0


def ours_marcel(i, sname):
    """5/4/3 Marcel + K ballast + age curve on our own values."""
    N = int(sname[7:11])
    cur = ours[sname]
    pm = defaultdict(list)
    for _k, (v, _g, grp, _pid) in cur.items():
        pm[grp].append(v)
    pm = {g: sum(v) / len(v) for g, v in pm.items()}
    out = {}
    for k, (_v, _g, grp, pid) in cur.items():
        num = den = 0.0
        for w, back in ((5, 0), (4, 1), (3, 2)):
            j = i - back
            if j < 0:
                continue
            prev = ours[SEASONS[j]].get(k)
            if prev:
                num += w * prev[1] * prev[0]
                den += w * prev[1]
        shrunk = (num + K * pm.get(grp, 0.0)) / (den + K)
        a = age_at(pid, N + 1)
        out[k] = shrunk + (sm.get((grp, round(a)), 0.0) if a else 0.0)
    return out


name2pid = {}
for _pid, _h in ch.items():
    _full = f"{_h.get('first_name', '')} {_h.get('last_name', '')}"
    _pos = "D" if (_h.get("position") or "") == "D" else "F"
    name2pid[(_norm_name(_full), _pos)] = _pid

# ---------------------------------------------------------------------------
# BYO entrants
# ---------------------------------------------------------------------------


def load_entrant(path):
    """Normalized entrant CSV -> {year: {(name, pos): (rate82, gp)}}.
    Duplicate (player, season) rows (multi-team seasons) aggregate."""
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            year = int(r["season"])
            gp = int(float(r["gp"] or 0))
            pos = "D" if "D" in (r["position"] or "").upper() else "F"
            key = (_norm_name(r["player"]), pos)
            agg[year][key][0] += gp
            agg[year][key][1] += float(r["value"] or 0)
    return {y: {k: (v[1] / v[0] * 82, v[0]) for k, v in d.items()
                if v[0] >= MIN_GP} for y, d in agg.items()}


def marcel(series, year, age_scale=1.0):
    """5/4/3 Marcel + K ballast + age curve for an entrant series
    ({year: {key: (rate, gp)}}). Missing history years just
    contribute fewer terms."""
    cur = series.get(year, {})
    pm = defaultdict(list)
    for k, (r, _g) in cur.items():
        pm[k[1]].append(r)
    pm = {g_: sum(v) / len(v) for g_, v in pm.items()}
    out = {}
    for k, (_r, _g) in cur.items():
        num = den = 0.0
        for w, back in ((5, 0), (4, 1), (3, 2)):
            prev = series.get(year - back, {}).get(k)
            if prev:
                num += w * prev[1] * prev[0]
                den += w * prev[1]
        shrunk = (num + K * pm.get(k[1], 0.0)) / (den + K)
        pid = name2pid.get(k)
        a = age_at(pid, year + 1) if pid else None
        out[k] = shrunk + (sm.get((k[1], round(a)), 0.0) * age_scale
                           if a else 0.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest",
                    default=str(DATA / "entrants/entrants.json"))
    args = ap.parse_args()

    entrants = []
    mpath = Path(args.manifest)
    if mpath.is_file():
        spec = json.loads(mpath.read_text(encoding="utf-8-sig"))
        for e in spec.get("entrants", []):
            name = e["name"]
            csv_path = REPO / e["csv"] if not Path(e["csv"]).is_absolute() \
                else Path(e["csv"])
            if not csv_path.is_file():
                print(f"SKIP {name}: {e['csv']} not found")
                continue
            series = load_entrant(csv_path)
            missing = REQUIRED_YEARS - set(
                y for y, d in series.items() if d)
            if missing:
                print(f"SKIP {name}: missing seasons "
                      f"{sorted(missing)} (needs 2022-2025)")
                continue
            entrants.append((name, series,
                             float(e.get("age_scale", 1.0))))
            hist = sorted(y for y in series if y < 2022)
            print(f"entrant {name}: seasons "
                  f"{sorted(series)}, marcel history {hist or 'none'}")
    else:
        print(f"no manifest at {mpath}; running ours-only smoke")

    pred_names = ["ours", "ours-marcel"]
    for name, _, _ in entrants:
        pred_names += [name, f"{name}-marcel"]
    judge_names = ["ours"] + [name for name, _, _ in entrants]

    acc = defaultdict(list)
    season_of = {int(s[7:11]): s for s in SEASONS}
    season_of[2025] = "season_2025_26"
    for N in TRANSITIONS:
        sname, sname1 = season_of[N], season_of[N + 1]
        i = SEASONS.index(sname)
        preds = {
            "ours": {k: v[0] for k, v in ours[sname].items()},
            "ours-marcel": ours_marcel(i, sname),
        }
        judges = {"ours": {k: v[0] for k, v in ours[sname1].items()}}
        for name, series, ascale in entrants:
            preds[name] = {k: v[0] for k, v in series[N].items()}
            preds[f"{name}-marcel"] = marcel(series, N, ascale)
            judges[name] = {k: v[0] for k, v in series[N + 1].items()}
        common = None
        for d in list(preds.values()) + list(judges.values()):
            ks = set(d.keys())
            common = ks if common is None else (common & ks)
        common = sorted(common)
        print(f"{N}->{N + 1}: common sample {len(common)}")
        for pn, p in preds.items():
            for jn, jd in judges.items():
                acc[(pn, jn)].append(_spearman(
                    [p[k] for k in common], [jd[k] for k in common]))

    nt = len(TRANSITIONS)
    pw = max(len(p) for p in pred_names) + 2
    jw = max(8, max(len(j) for j in judge_names) + 1)
    print(f"\nTOURNAMENT (mean Spearman rho, {nt} transitions, "
          "strict common sample)")
    print(" " * pw + " | " + "".join(f"{j:>{jw}s}" for j in judge_names)
          + f"{'rowmean':>9s}")
    for pn in pred_names:
        vals = [sum(acc[(pn, j)]) / nt for j in judge_names]
        print(f"{pn:>{pw}s} | "
              + "".join(f"{v:+{jw}.3f}" for v in vals)
              + f"{sum(vals) / len(vals):+9.3f}")
    print("\nper-transition breakdown:")
    for ti, N in enumerate(TRANSITIONS):
        print(f"\n{N}->{N + 1}")
        print(" " * pw + " | "
              + "".join(f"{j:>{jw}s}" for j in judge_names))
        for pn in pred_names:
            vals = [acc[(pn, j)][ti] for j in judge_names]
            print(f"{pn:>{pw}s} | "
                  + "".join(f"{v:+{jw}.3f}" for v in vals))

    print("\ncolumn winners:")
    for j in judge_names:
        best = max(pred_names, key=lambda p: sum(acc[(p, j)]) / nt)
        print(f"  {j}: {best} ({sum(acc[(best, j)]) / nt:+.3f})")
    print("\nmonkey law check (raw vs its own marcel, rowmean):")
    for name, _, _ in entrants:
        raw = sum(sum(acc[(name, j)]) / nt
                  for j in judge_names) / len(judge_names)
        mar = sum(sum(acc[(f'{name}-marcel', j)]) / nt
                  for j in judge_names) / len(judge_names)
        verdict = "MONKEY WINS" if mar > raw else "raw survives"
        print(f"  {name}: raw {raw:+.3f} vs marcel {mar:+.3f} "
              f"-> {verdict}")


if __name__ == "__main__":
    main()
