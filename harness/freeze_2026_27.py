"""Generate the frozen 2026-27 projections — THE freeze artifact.

    python harness/freeze_2026_27.py

Writes data/projections_2026_27.csv: our projected 2026-27 value
(WAR-style, per-82) for every skater with 30+ GP in 2025-26.

The recipe is exactly the tournament's Marcel — the same one every
entrant faces — launched from the final shipped season:

    5/4/3 GP-weighted average over 2025-26 / 2024-25 / 2023-24,
    K=40 ballast toward the 2025-26 positional mean,
    plus the smoothed positional age delta at Oct 1, 2026.

Every input ships in this repo (data/ours_values.csv,
data/players.csv; the age table derives from them inside
run_tournament), and the script is deterministic — rerun it and
diff against the committed file to verify the freeze was produced
by the stated recipe and nothing else.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from run_tournament import DATA, K, age_at, ch, ours, sm

LAUNCH = "season_2025_26"                  # history anchor
HISTORY = [(5, "season_2025_26"), (4, "season_2024_25"),
           (3, "season_2023_24")]
PROJECT_YEAR = 2026                        # the 2026-27 season
OUT = DATA / "projections_2026_27.csv"


def main() -> None:
    cur = ours[LAUNCH]
    pm = defaultdict(list)
    for _k, (rate, _gp, grp, _pid) in cur.items():
        pm[grp].append(rate)
    pm = {g: sum(v) / len(v) for g, v in pm.items()}

    rows = []
    for k, (rate25, gp25, grp, pid) in cur.items():
        num = den = 0.0
        for w, sname in HISTORY:
            prev = ours[sname].get(k)
            if prev:
                num += w * prev[1] * prev[0]
                den += w * prev[1]
        shrunk = (num + K * pm[grp]) / (den + K)
        a = age_at(pid, PROJECT_YEAR)
        proj = shrunk + (sm.get((grp, round(a)), 0.0) if a else 0.0)
        h = ch.get(pid) or {}
        name = f"{h.get('first_name', '')} {h.get('last_name', '')}".strip()
        rows.append([pid, name, grp, gp25, round(rate25, 3),
                     round(proj, 3)])

    rows.sort(key=lambda r: (-r[5], r[0]))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "player", "position_group", "gp_2025_26",
                    "war82_2025_26", "projected_war82_2026_27"])
        w.writerows(rows)
    print(f"wrote {OUT.relative_to(Path(__file__).resolve().parent.parent)}"
          f" ({len(rows)} skaters)")
    print("top of the projection:")
    for r in rows[:8]:
        print(f"  {r[1]:24s} {r[2]}  {r[5]:+.3f}")


if __name__ == "__main__":
    main()
