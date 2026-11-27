#!/usr/bin/env python3
"""The capacity test in one table (docs/plan-load-test.md §5, §9): every step's checks side by
side, the highest step where all of them held, and the step where each one first broke.

    python3 perf/summary.py <capacity run folder>

It reads the verdict-<k>x.json files perf/report.py --step wrote (or step folders' verdict.json)."""
import glob
import json
import os
import sys


def summary(run: str) -> str:
    steps = []
    for p in sorted(glob.glob(os.path.join(run, "verdict-*.json"))
                    + glob.glob(os.path.join(run, "*", "verdict.json"))):
        with open(p) as f:
            steps.append(json.load(f))
    if not steps:
        return f"{run}: no step has a verdict.json yet"
    steps.sort(key=lambda s: s["mult"])
    checks = list(dict.fromkeys(c["check"] for s in steps for c in s["checks"]))
    lines = ["# Capacity test: the steps side by side\n",
             "| Check | " + " | ".join(f"{s['mult']:g}x" for s in steps) + " |",
             "|---|" + "---|" * len(steps)]
    first_break = {}
    for check in checks:
        cells = []
        for s in steps:
            c = next((x for x in s["checks"] if x["check"] == check), None)
            if c is None:
                cells.append("–")
                continue
            word = "N/A " if c["pass"] is None else "PASS " if c["pass"] else "**FAIL** "
            cells.append(word + str(c["measured"]))
            if c["pass"] is False and check not in first_break:
                first_break[check] = s["mult"]
        lines.append(f"| {check} | " + " | ".join(cells) + " |")
    held = [s["mult"] for s in steps if s["pass"]]
    top = 0.0
    for s in steps:                      # the highest step with every step up to it passing
        if not s["pass"]:
            break
        top = s["mult"]
    lines += ["", f"- Every check held up to **{top:g}x**" if top else
              "- Not every check held even at the first step",
              f"- Steps that passed: {', '.join(f'{m:g}x' for m in held) or 'none'}"]
    for check, mult in first_break.items():
        lines.append(f"- {check}: first broke at {mult:g}x")
    facts = [(s["mult"], s.get("facts", {})) for s in steps]
    lines += ["", "| Step | API p95 ms | PDF p95 s | memory peak MiB | CPU p95 % | "
              "database MiB | connections |", "|---|---|---|---|---|---|---|"]
    for mult, f in facts:
        lines.append(f"| {mult:g}x | {f.get('api_p95_ms', float('nan')):.0f} | "
                     f"{f.get('pdf_p95_s', float('nan')):.1f} | "
                     f"{f.get('memory_peak_mib', float('nan')):.0f} | "
                     f"{f.get('cpu_p95_pct', float('nan')):.0f} | "
                     f"{f.get('db_mib', float('nan')):.0f} | "
                     f"{f.get('db_connections_max', float('nan')):.0f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(sys.argv[1]))
