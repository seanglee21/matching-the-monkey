# Matching the Monkey — the tournament harness

This is the evaluation harness behind *Matching the Monkey*
(Pacific Coast Labs, 2026 — [Zenodo DOI, v2](https://doi.org/10.5281/zenodo.22806882)).
It races hockey player metrics against each other, and against a
deliberately dumb baseline, under one fixed protocol. Our own
model's values ship in this repo as the built-in entrant. Everyone
else is bring-your-own-data.

One command:

```
python harness/run_tournament.py
```

With no other data present, that runs the built-in smoke test:
our raw values against our projection, judged by our own
next-season values. Smoke numbers use the full built-in sample;
the published table appears once entrants are added, because the
strict common sample re-restricts every column. Add entrants and
the tournament grows.

## The protocol

Fixed, identical to the paper:

- WAR-style season totals converted to per-82 rates
- skaters with 30+ GP; goalies excluded
- strict common sample: every player scored by EVERY predictor
  and judge column, or dropped
- Spearman rank correlation of each predictor against each
  judge's next-season values
- mean over three transitions: 2022→23, 2023→24, 2024→25
- every entrant also enters as its own Marcel: 5/4/3 weighting
  over up to three prior seasons, ballast K=40 toward the
  positional mean, and an age adjustment (the age-delta table is
  derived inside the harness from the shipped values; entrants in
  other units pass `age_scale` in the manifest)

The monkey law: if a metric's raw number loses to a Marcel built
from that metric's own history, on that metric's own scoreboard,
the raw number is describing the past, not predicting the future.

## Bring your own entrants

Nothing third-party ships in this repo. You obtain files from
their publishers yourself and drop them under `data/`:

- **Evolving-Hockey** (subscriber export): `data/eh/eh_gar_skaters_2007_2026.csv`
- **HockeyStats** (public download): `data/hockeystats/WAR (1).csv`
- **MoneyPuck** (public download, or `--fetch-mp`): `data/mp/skaters_<year>_snap<date>.csv`
- **Hockey Alchemy** (public API): `data/hockey_alchemy/snap_<date>/gar_leaders_<YYYYYYYY>.json`

Then:

```
python harness/make_entrants.py
python harness/run_tournament.py
```

`make_entrants.py` converts whatever it finds into normalized
entrant CSVs and writes the manifest; missing sources are skipped
with a note. Your own metric enters without any converter: write
a CSV with columns `player,season,position,gp,value` (season =
start year, e.g. 2022 for 2022-23) and add it to
`data/entrants/entrants.json`.

The layering, stated plainly: the normalized CSV is the
interface, and `make_entrants.py` is the reference
implementation of the normalization for the four shops above.
Normalization choices are part of the protocol — multi-team
seasons aggregate, MoneyPuck rows filter to the all-situations
line, and each shop's value field is named in the converter — so
to reproduce the published table, run the converters on the
named source files rather than hand-rolling CSVs. Your own
metric needs only the CSV spec. If a shop changes its format,
the converter stops loudly instead of converting wrong numbers
next to someone's name.

An entrant needs seasons 2022-2025 to be graded; seasons back to
2019, when present, feed its Marcel.

## What ships here

- `harness/` — the tournament runner and the entrant converters
- `data/ours_values.csv` — our per-season player values (the
  paper's pWAR individual component), one row per player-season
- `data/players.csv` — the join list: player name, position
  class, and birth date per NHL player id (factual data from the
  NHL's public API; joins to third-party files are by normalized
  name + position)

## The bet

Our 2026-27 projections freeze in a public, timestamped commit
before opening night, with the scoring rules pre-registered. In
April 2027 the table reruns on the season that actually
happened: us, the incumbents, and the monkey. If we lose to the
monkey, that gets published too.

## License

Code: MIT (see LICENSE). Our values in `data/` are released
CC BY 4.0 — cite the paper. Player names and birth dates are
facts from the NHL's public API. No third-party metric data is
included or redistributed here.
