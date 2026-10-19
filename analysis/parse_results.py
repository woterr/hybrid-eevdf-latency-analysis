#!/usr/bin/env python3
"""Parse schbench logs from the phase 2 N=30 runs into a clean CSV.

The log files contain several blocks per run (10s and 15s runtime). We only
care about the last "Wakeup Latencies" block, since that is the full run.

Usage:
    python3 analysis/parse_results.py [results_dir]

Defaults to the phase 2 results directory shipped in this repo.
"""
import csv
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_RESULTS = os.path.join(ROOT, "phase2", "rigorous_results_20261019_212023")

FIELDS = [
    ("p50", 50.0),
    ("p90", 90.0),
    ("p99", 99.0),
    ("p999", 99.9),
]


def parse_wakeup_block(path):
    """Return dict with p50/p90/p99/p999/max (usec) from the last wakeup block."""
    lines = open(path, errors="replace").read().splitlines()
    starts = [i for i, l in enumerate(lines) if "Wakeup Latencies" in l]
    if not starts:
        return None
    start = starts[-1]
    block = []
    for line in lines[start + 1:]:
        if "Request Latencies" in line:
            break
        block.append(line)
    text = "\n".join(block)
    found = {float(p): int(v) for p, v in re.findall(r"(\d+(?:\.\d)?)th:\s+(\d+)", text)}
    out = {name: found.get(pct) for name, pct in FIELDS}
    m = re.search(r"max=(\d+)", text)
    out["max"] = int(m.group(1)) if m else None
    m = re.search(r"\((\d+) total samples\)", lines[start])
    out["samples"] = int(m.group(1)) if m else None
    return out


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    return statistics.median(vals) if vals else None


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESULTS
    rows = []
    for i in range(1, 31):
        row = {"run": i}
        for exp in ("exp_a", "exp_b"):
            path = os.path.join(results, exp, "run_%d.log" % i)
            data = parse_wakeup_block(path) if os.path.exists(path) else None
            for key, _ in FIELDS:
                row["%s_%s" % (exp, key)] = data[key] if data else None
            row["%s_max" % exp] = data["max"] if data else None
            row["%s_samples" % exp] = data["samples"] if data else None
        rows.append(row)

    cols = ["run"]
    for exp in ("exp_a", "exp_b"):
        for key, _ in FIELDS:
            cols.append("%s_%s" % (exp, key))
        cols.append("%s_max" % exp)
        cols.append("%s_samples" % exp)

    out_csv = os.path.join(HERE, "distribution_data.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c) for c in cols})

    lines = []
    lines.append("wakeup latency summary, N=30 per experiment")
    lines.append("source: %s" % results)
    lines.append("")
    for exp, label in (("exp_a", "Exp A floating 0-17"), ("exp_b", "Exp B pinned E 12-17")):
        for key, pct in FIELDS:
            vals = [r["%s_%s" % (exp, key)] for r in rows if r["%s_%s" % (exp, key)] is not None]
            if not vals:
                continue
            pct_label = ("%g" % pct)
            lines.append(
                "%-22s %-10s median=%-6s min=%-6s max=%-6s n=%d"
                % (label, "p" + pct_label, median(vals), min(vals), max(vals), len(vals))
            )
        maxes = [r["%s_max" % exp] for r in rows if r["%s_max" % exp] is not None]
        lines.append(
            "%-22s %-10s median=%-6s min=%-6s max=%-6s n=%d"
            % (label, "max", median(maxes), min(maxes), max(maxes), len(maxes))
        )
        p999 = [r["%s_p999" % exp] for r in rows if r["%s_p999" % exp] is not None]
        for thresh in (250, 500, 1000, 2000):
            lines.append(
                "%-22s p99.9 > %4d us: %d/%d runs" % (label, thresh, sum(1 for v in p999 if v > thresh), len(p999))
            )
        lines.append("")

    out_txt = os.path.join(HERE, "SUMMARY_STATS.txt")
    with open(out_txt, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("wrote", out_csv)
    print("wrote", out_txt)
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
