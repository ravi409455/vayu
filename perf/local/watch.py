#!/usr/bin/env python3
"""Live view of a local load-test run, refreshed every 5 s (Ctrl+C to quit).

    python3 perf/local/watch.py [run folder]     (default: the newest in perf/local/results)"""
import csv
import glob
import math
import os
import subprocess
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
run = sys.argv[1] if len(sys.argv) > 1 else max(glob.glob(os.path.join(here, "results", "*/")),
                                                key=os.path.getmtime)


def rows(name):
    p = os.path.join(run, f"{name}.csv")
    try:
        return list(csv.reader(open(p)))
    except OSError:
        return []


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, math.ceil(0.95 * len(xs)) - 1)] if xs else float("nan")


while True:
    now = time.time()
    out = [f"Load test: {os.path.basename(run.rstrip('/'))}    {time.strftime('%H:%M:%S')}"]
    start = rows("run")
    if not start:
        out.append("Signing in the test users (the clock starts when all are in)...")
    else:
        mins = (now - float(start[0][0])) / 60
        phase = ("warm-up (not measured)" if mins < 25 else
                 "MEASURED window" if mins < 85 else "after the window")
        out.append(f"Clock: {mins:5.1f} min of 90   -> {phase}")

    reqs = [r for r in rows("requests") if now - float(r[0]) <= 60]
    server = [r for r in reqs if not r[2].startswith("file store")]
    ms = [float(r[3]) for r in server]
    errs = sum(r[4] == "0" for r in server)
    out += ["", "Server calls, last 60 s",
            f"  {len(server)} calls ({len(server) / 60:.1f}/s)   p95 {p95(ms):.0f} ms   "
            f"errors {errs}   file uploads {len(reqs) - len(server)}"]

    ins = rows("inspections")
    begun = sum(r[2] == "begin" for r in ins)
    sub = sum(r[2] == "submitted" for r in ins)
    failed = [r for r in ins if r[2].startswith("failed")]
    out += ["", f"Inspections: {begun} started, {sub} submitted, {len(failed)} failed"]
    out += [f"  FAILED: {r[2][:90]}" for r in failed[-3:]]

    pdf = rows("pdf")
    out += ["", f"PDFs ready: {len(pdf)}   last: " +
            ", ".join(f"{r[2]} {r[3]}s" for r in pdf[-6:])]

    hooks = rows("webhooks")
    d = [float(r[3]) for r in hooks[-200:] if r[3]]
    out += ["", f"Webhooks arrived: {len(hooks)}   recent p95 delay {p95(d):.2f} s"]

    up = rows("uploads")
    out += ["", f"Files sent: {len(up)}"]

    stats = subprocess.run(["docker",  # noqa: S607 - the laptop's own docker "stats", "--no-stream", "--format",
                            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
                           capture_output=True, text=True).stdout.splitlines()
    out += ["", "Server containers (CPU % of the pinned core, memory)"]
    out += [f"  {s}" for s in stats if s.startswith("vayu-") and not s.startswith("vayu-s3")]

    print("\033[2J\033[H" + "\n".join(out), flush=True)
    time.sleep(5)
