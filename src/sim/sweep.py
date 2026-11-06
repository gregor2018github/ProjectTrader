"""Many seeds, many years: the health report over a sweep of headless runs.

    python -m src.sim.sweep                          # 20 seeds x 50 years into runs/sweep
    python -m src.sim.sweep --seeds 5 --years 10 --out runs/quick
    python -m src.sim.sweep --reuse --out runs/sweep # re-check runs already written

runs seeds ``--first-seed`` .. ``--first-seed + --seeds - 1`` as new games
(``python -m src.sim.run``, each into ``<out>/seed<N>/``), in parallel
processes, then applies every check of ``src.sim.health`` to each run and
writes, besides printing the tables:

- ``<out>/summary.md``: per check, how many seeds were ok, warned or failed,
  the median and the worst seed's headline number; a grid of every check's
  status per seed; the worst seed's finding for every check that missed; and
  the tradability per good, its median over the seeds;
- ``<out>/summary.csv``: one row per seed and check (status, value, text), to
  compare sweeps.

Exits with 1 when any seed fails a check (warnings never fail), so it can gate
a calibration change: run it before and after, and compare the summaries.
"""
import argparse
import csv
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import health
from .data import Definitions, ScenarioDef
from .run import META_FILE, SCENARIO, load_definitions, write_run
from .scenario.tmx_town import load_town
from .state import TownSpec

SUMMARY_MD = "summary.md"
SUMMARY_CSV = "summary.csv"
MARK = {health.OK: ".", health.WARN: "w", health.FAIL: "F"}     # the grid's marks


@dataclass
class SeedResult:
    seed: int
    findings: List[health.Finding]
    tradability: List[health.Tradability]
    seconds: float              # simulating it (0 when reused)


def seed_dir(out: str, seed: int) -> str:
    return os.path.join(out, f"seed{seed}")


def run_seed(seed: int, years: float, out: str, definitions: Definitions, town: TownSpec,
             scenario: Optional[ScenarioDef], reuse: bool) -> SeedResult:
    """Simulate one seed (unless *reuse* and it is there) and check it. Runs in a worker process."""
    folder = seed_dir(out, seed)
    seconds = 0.0
    if not (reuse and os.path.exists(os.path.join(folder, META_FILE))):
        began = time.perf_counter()
        write_run(folder, years, seed, definitions, town, scenario)
        seconds = time.perf_counter() - began
    data = health.RunData.load(folder)
    return SeedResult(seed, health.evaluate(data), health.tradability(data.goods), seconds)


def sweep(seeds: Sequence[int], years: float, out: str, jobs: int, reuse: bool = False,
          map_path: Optional[str] = None, scenario_name: str = SCENARIO) -> List[SeedResult]:
    """Run and check every seed, *jobs* at a time; the results in seed order."""
    definitions, scenario = load_definitions(scenario_name)
    town = load_town(map_path)
    results: List[SeedResult] = []
    began = time.perf_counter()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_seed, s, years, out, definitions, town, scenario, reuse) for s in seeds]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            fails = [f.check for f in r.findings if f.status == health.FAIL]
            warns = [f.check for f in r.findings if f.status == health.WARN]
            took = f"{r.seconds:5.1f} s" if r.seconds else " reused"
            print(f"  [{len(results):>{len(str(len(seeds)))}}/{len(seeds)}] seed {r.seed:>3}: {took}, "
                  f"{len(fails)} failed{': ' + ', '.join(fails) if fails else ''}, {len(warns)} warnings",
                  flush=True)
    print(f"  {len(seeds)} runs in {time.perf_counter() - began:.1f} s ({jobs} at a time)")
    return sorted(results, key=lambda r: r.seed)


# -- the tables -------------------------------------------------------------------

def _num(value: float) -> str:
    """A headline number, short: whole numbers as such, small shares in scientific notation."""
    if value != value or value in (float("inf"), float("-inf")):
        return str(value)
    if value == int(value) and abs(value) < 1e6:
        return str(int(value))
    if abs(value) < 1e-3:
        return f"{value:.1e}"
    return f"{value:.3g}"


@dataclass
class CheckRow:
    check: health.Check
    counts: Dict[str, int]
    median: float
    worst: health.Finding
    worst_seed: int


def tally(results: Sequence[SeedResult]) -> List[CheckRow]:
    """Per check, over the seeds: how many ok, warned, failed; the median value; the worst seed."""
    rows = []
    for i, c in enumerate(health.CHECKS):
        per_seed = [(r.seed, r.findings[i]) for r in results]
        counts = {s: sum(f.status == s for _, f in per_seed) for s in (health.OK, health.WARN, health.FAIL)}
        # The worst seed: one that missed before one that did not, then by the headline number
        pick = max if c.higher_is_worse else min
        missed = [p for p in per_seed if not p[1].ok] or per_seed
        seed, worst = pick(missed, key=lambda p: p[1].value)
        rows.append(CheckRow(c, counts, statistics.median(f.value for _, f in per_seed), worst, seed))
    return rows


def tradability_table(results: Sequence[SeedResult]) -> List[Tuple[str, float, float, float]]:
    """Per good: the median over seeds of its median range and of its share of days worth a round trip, and the best seed's share."""
    by_good: Dict[str, List[health.Tradability]] = {}
    for r in results:
        for t in r.tradability:
            by_good.setdefault(t.good, []).append(t)
    table = [(good, statistics.median(t.median_range for t in ts), statistics.median(t.share_worth_it for t in ts),
              max(t.share_worth_it for t in ts)) for good, ts in by_good.items()]
    return sorted(table, key=lambda row: -row[1])


def _md_table(header: Sequence[str], rows: Sequence[Sequence[str]], align: str) -> List[str]:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(":---" if a == "l" else "---:" if a == "r" else ":---:" for a in align) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _text_table(header: Sequence[str], rows: Sequence[Sequence[str]], align: str) -> List[str]:
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)]

    def line(cells):
        return "  ".join(c.ljust(w) if a == "l" else c.rjust(w) if a == "r" else c.center(w)
                         for c, w, a in zip(cells, widths, align)).rstrip()
    return [line(header), line(["-" * w for w in widths])] + [line(r) for r in rows]


def summary(results: Sequence[SeedResult], years: float, markdown: bool) -> str:
    """The sweep's report, as markdown (summary.md) or as plain text (the console)."""
    table = _md_table if markdown else _text_table
    seeds = [r.seed for r in results]
    rows = tally(results)
    out: List[str] = []
    title = f"Health over {len(seeds)} seeds x {years:g} years (seeds {seeds[0]}-{seeds[-1]})" if seeds else "No runs"
    out += [f"# {title}" if markdown else title, ""]
    fails = sum(r.counts[health.FAIL] for r in rows)
    warns = sum(r.counts[health.WARN] for r in rows)
    failing = [r.check.name for r in rows if r.counts[health.FAIL]]
    out += [f"{len(seeds) * len(rows)} checks: {fails} failed" + (f" ({', '.join(failing)})" if failing else "")
            + f", {warns} warnings.", ""]

    out += table(["check", "kind", "threshold", "ok", "warn", "fail", "median", "worst", "seed", "unit"],
                 [[r.check.name, r.check.severity.lower(), r.check.threshold, str(r.counts[health.OK]),
                   str(r.counts[health.WARN]), str(r.counts[health.FAIL]), _num(r.median), _num(r.worst.value),
                   str(r.worst_seed), r.check.unit] for r in rows], "lllrrrrrrl")

    out += ["", "## Per seed" if markdown else "Per seed (. ok, w warning, F failed)", ""]
    if markdown:
        out += ["`.` ok, `w` warning, `F` failed.", ""]
    grid = [[r.check.name] + [MARK[res.findings[i].status] for res in results] for i, r in enumerate(rows)]
    out += table(["check"] + [str(s) for s in seeds], grid, "l" + "c" * len(seeds))

    missed = [r for r in rows if r.worst.status != health.OK]
    if missed:
        out += ["", "## Worst cases" if markdown else "Worst cases", ""]
        for r in missed:
            line = f"seed {r.worst_seed}, {r.check.name} [{r.worst.status}]: {r.worst.text}"
            out.append(f"- {line}" if markdown else f"  {line}")

    trade = tradability_table(results)
    if trade:
        out += ["", "## Tradability" if markdown else "Tradability", "",
                f"Median over the seeds of each run's median {health.TRADE_WINDOW_DAYS}-day price range, and of the "
                f"share of days that range beats 2 x the round trip of a {health.TRADE_LOT_VALUE:g}g lot "
                f"(best seed's share beside it).", ""]
        out += table(["good", "range", "worth it", "best seed"],
                     [[g, f"{rng:.1%}", f"{share:.1%}", f"{best:.1%}"] for g, rng, share, best in trade], "lrrr")
    return "\n".join(out) + "\n"


def write_csv(path: str, results: Sequence[SeedResult]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["seed", "check", "status", "value", "text"])
        for r in results:
            for finding in r.findings:
                writer.writerow([r.seed, finding.check, finding.status, repr(float(finding.value)), finding.text])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.sim.sweep", description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, default=20, help="how many seeds (default 20)")
    parser.add_argument("--first-seed", type=int, default=1, help="the first seed (default 1)")
    parser.add_argument("--years", type=float, default=50, help="game years per run (default 50)")
    parser.add_argument("--out", default=os.path.join("runs", "sweep"), help="output folder (default runs/sweep)")
    parser.add_argument("--jobs", type=int, default=0, help="runs at a time (default: one per CPU, at most --seeds)")
    parser.add_argument("--reuse", action="store_true", help="check runs already in --out instead of simulating them")
    parser.add_argument("--map", help="the .tmx map to take the town from (default the game's)")
    parser.add_argument("--scenario", default=SCENARIO, help="assets/data/scenarios/<name>.json (default home_town)")
    args = parser.parse_args(argv)
    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    jobs = args.jobs or max(1, min(len(seeds), os.cpu_count() or 1))
    print(f"Sweep: {len(seeds)} seeds x {args.years:g} years -> {args.out}")
    results = sweep(seeds, args.years, args.out, jobs, args.reuse, args.map, args.scenario)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, SUMMARY_MD), "w", encoding="utf-8") as f:
        f.write(summary(results, args.years, markdown=True))
    write_csv(os.path.join(args.out, SUMMARY_CSV), results)
    print()
    print(summary(results, args.years, markdown=False))
    print(f"-> {os.path.join(args.out, SUMMARY_MD)}, {os.path.join(args.out, SUMMARY_CSV)}")
    return 1 if any(f.status == health.FAIL for r in results for f in r.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
