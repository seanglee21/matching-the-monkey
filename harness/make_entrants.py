"""Convert locally-obtained public metrics into tournament entrants.

The artifact redistributes nothing third-party. This script converts
files YOU obtained from their publishers into the normalized entrant
CSVs that run_tournament.py reads, and writes the entrant manifest.
Every converter is skipped silently-with-a-note when its source
isn't present — bring what you have, the tournament sizes to it.

Known shops and where their files go (paths under data/):

- Evolving-Hockey (subscriber export, not redistributable):
    data/eh/eh_gar_skaters_2007_2026.csv
- HockeyStats.com (public download):
    data/hockeystats/WAR (1).csv
- MoneyPuck (public download, or --fetch-mp to pull live):
    data/mp/skaters_<year>_snap<date>.csv
- Hockey Alchemy (public API snapshot):
    data/hockey_alchemy/snap_<date>/gar_leaders_<YYYYYYYY>.json

Your own metric: skip this script — write a normalized CSV
(player,season,position,gp,value; season = start year) and add it
to the manifest by hand.

Usage:
    python harness/make_entrants.py [--fetch-mp]
"""
import argparse
import csv
import io
import json
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = DATA / "entrants"
YEARS = range(2019, 2026)


def parse_season(s):
    """'22-23' / '2022-23' / '20222023' / '2022' -> 2022."""
    s = (s or "").strip()
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return int(digits[:4])
    if len(digits) == 6:
        return int(digits[:4])
    if len(digits) == 4 and "-" in s:          # '22-23'
        y = int(digits[:2])
        return 2000 + y if y < 90 else 1900 + y
    if len(digits) == 4:
        return int(digits)
    raise ValueError(f"unparseable season: {s!r}")


def format_drift(name, missing, found):
    """A shop changed its file format: stop loudly, never convert
    silently-wrong data. A zeroed or misparsed entrant would put
    wrong numbers next to someone's name."""
    print(f"ERROR: {name} format drift — expected column(s) "
          f"{missing} not found.")
    print(f"  columns present: {sorted(found)}")
    print("  The source format may have changed since this "
          "converter was written (September 2026). Either adjust "
          "the converter, or normalize the file yourself to the "
          "entrant CSV spec (player,season,position,gp,value) and "
          "add it to data/entrants/entrants.json by hand.")
    raise SystemExit(2)


def sanity_check_values(name, rows):
    """Post-conversion guard: a column-mapping mistake typically
    yields all-zero values. Refuse to write them."""
    if not rows:
        return
    nonzero = sum(1 for r in rows if r[4])
    if nonzero < max(1, len(rows) // 10):
        print(f"ERROR: {name} conversion produced "
              f"{len(rows) - nonzero}/{len(rows)} zero values — "
              "the value column mapping looks wrong. Refusing to "
              "write a garbage entrant.")
        raise SystemExit(2)


def write_rows(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player", "season", "position", "gp", "value"])
        w.writerows(rows)
    print(f"wrote {path.relative_to(REPO)} ({len(rows)} rows)")
    return True


def convert_season_column_csv(name, src, pk, sk, wk, gk, posk):
    """Single CSV with a season column (EH / HockeyStats shape)."""
    if not src.is_file():
        print(f"skip {name}: {src.relative_to(REPO)} not found")
        return False
    rows = []
    with open(src, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        need = {pk, sk, wk, gk, posk}
        have = set(reader.fieldnames or [])
        if not need <= have:
            format_drift(name, sorted(need - have), have)
        for r in reader:
            pos = (r.get(posk) or "").upper()
            if pos.startswith("G"):
                continue
            try:
                year = parse_season(r.get(sk))
                gp = int(float(r.get(gk, 0) or 0))
                val = float(r.get(wk) or 0)
            except ValueError:
                continue
            rows.append([r.get(pk, ""), year,
                         "D" if "D" in pos else "F", gp, val])
    sanity_check_values(name, rows)
    return write_rows(name, rows)


def convert_mp(fetch):
    rows = []
    for year in YEARS:
        snaps = sorted(DATA.glob(f"mp/skaters_{year}_snap*.csv"))
        if snaps:
            raw = snaps[-1].read_text(encoding="utf-8",
                                      errors="replace")
        elif fetch:
            print(f"fetching MoneyPuck {year} live "
                  "(unpinned input — snapshot it for records)")
            req = urllib.request.Request(
                "https://moneypuck.com/moneypuck/playerData/"
                f"seasonSummary/{year}/regular/skaters.csv",
                headers={"User-Agent": "Mozilla/5.0 (research)"})
            raw = urllib.request.urlopen(req, timeout=60).read() \
                .decode("utf-8")
        else:
            print(f"skip MP {year}: no local snapshot "
                  "(pass --fetch-mp to pull live)")
            continue
        reader = csv.DictReader(io.StringIO(raw))
        need = {"situation", "games_played", "gameScore", "name",
                "position"}
        have = set(reader.fieldnames or [])
        if not need <= have:
            format_drift("mp", sorted(need - have), have)
        for r in reader:
            if r.get("situation") != "all":
                continue
            try:
                gp = int(float(r.get("games_played", 0) or 0))
                val = float(r.get("gameScore", 0) or 0)
            except ValueError:
                continue
            pos = (r.get("position") or "").upper()
            rows.append([r.get("name", ""), year,
                         "D" if "D" in pos else "F", gp, val])
    if not rows:
        print("skip MP: nothing loaded")
        return False
    sanity_check_values("mp", rows)
    return write_rows("mp", rows)


def convert_ha():
    snaps = sorted(DATA.glob("hockey_alchemy/snap_*"))
    if not snaps:
        print("skip HA: no data/hockey_alchemy/snap_* directory")
        return False
    snap = snaps[-1]
    rows = []
    for year in YEARS:
        p = snap / f"gar_leaders_{year}{year + 1}.json"
        if not p.is_file():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        if "leaders" not in payload:
            format_drift("ha", ["leaders"], payload.keys())
        leaders = payload["leaders"]
        if leaders and not any("rapm_total_war" in r
                               for r in leaders[:25]):
            format_drift("ha", ["rapm_total_war"],
                         leaders[0].keys())
        for r in leaders:
            pos = (r.get("position") or "").upper()
            if pos == "G":
                continue
            gp = int(r.get("games_played") or 0)
            war = r.get("rapm_total_war")
            if war is None:
                continue
            rows.append([r.get("player_name", ""), year,
                         "D" if "D" in pos else "F", gp, float(war)])
    if not rows:
        print(f"skip HA: no gar_leaders files in {snap.name}")
        return False
    sanity_check_values("ha", rows)
    return write_rows("ha", rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-mp", action="store_true",
                    help="pull MoneyPuck seasons live when no local "
                         "snapshot exists")
    args = ap.parse_args()

    entrants = []
    if convert_season_column_csv(
            "eh", DATA / "eh/eh_gar_skaters_2007_2026.csv",
            "Player", "Season", "WAR", "GP", "Position"):
        entrants.append({"name": "EH", "csv": "data/entrants/eh.csv"})
    if convert_season_column_csv(
            "hs", DATA / "hockeystats/WAR (1).csv",
            "Player", "Season", "WAR", "GP", "Position"):
        entrants.append({"name": "HS", "csv": "data/entrants/hs.csv"})
    if convert_mp(args.fetch_mp):
        # game score runs ~8x WAR magnitude; rescale the age delta
        entrants.append({"name": "MP", "csv": "data/entrants/mp.csv",
                         "age_scale": 8.0})
    if convert_ha():
        entrants.append({"name": "HA", "csv": "data/entrants/ha.csv"})

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "entrants.json"
    manifest.write_text(
        json.dumps({"entrants": entrants}, indent=2) + "\n",
        encoding="utf-8")
    print(f"manifest: {manifest.relative_to(REPO)} "
          f"({len(entrants)} entrants)")


if __name__ == "__main__":
    main()
