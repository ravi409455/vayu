#!/usr/bin/env python3
"""Turn a load-test run's logs into the results (docs/plan-load-test.md §3, §9).

    python3 perf/report.py <run folder> [--from-min 25 --minutes 60] [--memory-mb 2048] [--cpus 1]

Reads requests.csv, pdf.csv, uploads.csv, inspections.csv, run.csv (the load script),
webhooks.csv (the receiver), stats.csv and host.csv (the sampler), verified.csv and stages.csv
(the server's own records, fetched after the run). The measured window starts --from-min after the
clock (the first inspections need 25 minutes to reach steady state) and lasts --minutes.
Prints the results (Markdown) and writes verdict.json into the run folder (perf/summary.py
puts the capacity steps side by side)."""
import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict

# the owner's numbers per hour at 1× (docs/plan-load-test.md §2); the load script multiplies them
PER_HOUR = {"new bookings": 18, "inspections submitted": 9, "PDFs made": 54,
            "external API calls": 6000, "webhooks delivered": 270}
LOAD_SHARE = 0.8        # a target counts as reached at 80% (small counts in one hour vary)
R2_PER_GB_MONTH, RETENTION_DAYS, INSPECTIONS_PER_DAY = 0.015, 90, 100


def args(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("run")
    a.add_argument("--from-min", type=float, default=25)
    a.add_argument("--minutes", type=float, default=60)
    a.add_argument("--memory-mb", type=float, default=2048)
    a.add_argument("--step", type=float, default=None,
                   help="a capacity run: measure the window run.csv recorded for this step")
    a.add_argument("--cpus", type=float, default=1,
                   help="the server's vCPUs (CPU 100%% = all of them)")
    return a.parse_args(argv)


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, math.ceil(p / 100 * len(xs)) - 1)]


def mib(s):
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", s.strip())
    if not m:
        return 0.0
    n, u = float(m.group(1)), m.group(2)
    return n * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "KB": 1 / 1024, "MB": 1, "GB": 1024}[u]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class Report:
    def __init__(self, o):
        self.o, self.lines, self.verdicts, self.facts = o, [], [], {}
        run = self.rows("run")
        if not run:
            raise SystemExit(f"{o.run}: no run.csv (the load script never started its clock)")
        self.t0, self.mult = float(run[0][0]), float(run[0][2]) if len(run[0]) > 2 else 1.0
        self.lo = self.t0 + o.from_min * 60
        self.hi = self.lo + o.minutes * 60
        if o.step is not None:          # the capacity step's own window, as the load script set it
            row = next((x for x in run if len(x) > 4 and x[1] == "step"
                        and float(x[2]) == o.step), None)
            if row is None:
                raise SystemExit(f"{o.run}: no step {o.step:g}x in run.csv")
            self.mult, self.lo, self.hi = o.step, float(row[3]), float(row[4])
            o.from_min, o.minutes = (self.lo - self.t0) / 60, (self.hi - self.lo) / 60
        # a run that ended earlier (a smoke run, a stopped step) is judged on what it ran
        last = max((float(r[0]) for r in self.rows("requests")), default=self.hi)
        self.cut = last < self.hi
        self.hi = min(self.hi, last)
        self.minutes = max((self.hi - self.lo) / 60, 0.0)

    def rows(self, name):
        p = os.path.join(self.o.run, f"{name}.csv")
        with open(p) if os.path.exists(p) else open(os.devnull) as f:
            return [r for r in csv.reader(f) if r]

    def inside(self, t):
        return self.lo <= float(t) < self.hi

    def say(self, text=""):
        self.lines.append(text)

    def verdict(self, name, ok, detail):
        """ok None: nothing to judge in this window (shown as N/A, not counted)."""
        self.verdicts.append({"check": name, "pass": None if ok is None else bool(ok),
                              "measured": detail})

    # ------------------------------------------------------------------ the load itself

    def load(self):
        """Did the run make the load it was meant to? Without this a PASS means nothing."""
        hours = self.minutes / 60
        made = {
            "new bookings": sum(1 for r in self.rows("requests") if self.inside(r[0])
                                and r[2] == "ext/bookings (create)" and r[4] == "1"),
            "inspections submitted": sum(1 for r in self.rows("inspections")
                                         if self.inside(r[0]) and r[2] == "submitted"),
            "PDFs made": sum(1 for r in self.rows("pdf")
                             if self.inside(r[0]) and r[3] != "timeout"),
            "external API calls": sum(1 for r in self.rows("requests") if self.inside(r[0])
                                      and r[2].startswith("ext/")),
            "webhooks delivered": sum(1 for r in self.rows("webhooks") if self.inside(r[0])),
        }
        self.say(f"## The load (at {self.mult:g}x, {self.minutes:.0f} minutes)\n")
        self.say("| What | Target | Made | Share |\n|---|---|---|---|")
        short = []
        for what, per_hour in PER_HOUR.items():
            want = per_hour * self.mult * hours
            share = made[what] / want if want else 1
            self.say(f"| {what} | {want:.0f} | {made[what]} | {share:.0%} |")
            # small counts in a short window vary by one either way: reached at 80% or one short
            if made[what] < min(LOAD_SHARE * want, want - 1):
                short.append(f"{what} {share:.0%}")
        self.say("")
        self.facts["load"] = made
        self.verdict(f"load as specified (each >= {LOAD_SHARE:.0%} of target)", not short,
                     ", ".join(short) or "all reached")

    # ------------------------------------------------------------------ answers

    def requests(self):
        by, errs, codes = defaultdict(list), defaultdict(int), Counter()
        for r in self.rows("requests"):
            t, _kind, name, ms, ok = r[:5]
            if not self.inside(t):
                continue
            by[name].append(float(ms))
            if ok == "0":
                errs[name] += 1
                codes[f"{name}: {r[5] if len(r) > 5 and r[5] else 'no answer'}"] += 1
        server = [ms for n, v in by.items() if not n.startswith("file store") for ms in v]
        server_err = sum(e for n, e in errs.items() if not n.startswith("file store"))
        self.say("## Server answers (ms)\n")
        self.say("| Call | p50 | p95 | max | count | errors |\n|---|---|---|---|---|---|")
        for n in sorted(by):
            v = by[n]
            self.say(f"| {n} | {pct(v, 50):.0f} | {pct(v, 95):.0f} | {max(v):.0f} | {len(v)} "
                     f"| {errs[n]} |")
        p95 = pct(server, 95)
        rate = 100 * server_err / max(len(server), 1)
        self.say(f"\nAll server calls: p95 {p95:.0f} ms, {len(server)} calls, {rate:.2f}% errors")
        if codes:
            self.say("\nErrors by call and answer: " + ", ".join(
                f"{k} ×{n}" for k, n in codes.most_common()))
        self.say("")
        self.facts["api_p95_ms"], self.facts["error_pct"] = p95, rate
        self.verdict("API p95 <= 500 ms", p95 <= 500, f"{p95:.0f} ms")
        self.verdict("errors < 1%", rate < 1, f"{rate:.2f}%")

    # ------------------------------------------------------------------ PDFs, files, webhooks

    def pdfs(self):
        big = {r[1] for r in self.rows("inspections") if len(r) > 4 and r[4] == "big"}
        pdfs, bigs, timeouts = defaultdict(list), [], 0
        for t, b, what, secs in (r[:4] for r in self.rows("pdf")):
            if not self.inside(t):
                continue
            if secs == "timeout":
                timeouts += 1
            elif b in big:
                bigs.append(float(secs))
            else:
                pdfs[what].append(float(secs))
        self.say("## PDF ready (seconds)\n")
        self.say("- first: from the expert's submit (includes the files' checks); regenerate: "
                 "from the press")
        for what, v in pdfs.items():
            self.say(f"- {what}: p50 {pct(v, 50):.1f}, p95 {pct(v, 95):.1f}, max {max(v):.1f} "
                     f"({len(v)} PDFs)")
        self.say(f"- timeouts (10 min): {timeouts}")
        self.say(f"- 150-photo reports: {', '.join(f'{x:.1f}' for x in bigs) or 'none'}\n")
        allp = [x for v in pdfs.values() for x in v]
        self.facts["pdf_p95_s"] = pct(allp, 95)
        self.verdict("PDF ready p95 <= 30 s", bool(allp) and pct(allp, 95) <= 30 and not timeouts,
                     f"{pct(allp, 95):.1f} s over {len(allp)} PDFs, {timeouts} timeouts")
        self.verdict("150-photo PDF <= 2 min", max(bigs) <= 120 if bigs else None,
                     f"worst {max(bigs):.1f} s over {len(bigs)}" if bigs else "none in this window")

    def uploads(self):
        sent = {r[1]: (float(r[0]), num(r[3]) if len(r) > 3 else None)
                for r in self.rows("uploads")}
        done = {r[0]: (num(r[1]), r[2]) for r in self.rows("verified")}
        delays = [done[i][0] - t for i, (t, _) in sent.items()
                  if self.inside(t) and i in done and done[i][0]]
        self.unchecked = [i for i in sent if done.get(i, (None, ""))[1] != "verified"]
        self.say("## Upload checked after sending (seconds)\n")
        self.say(f"- p50 {pct(delays, 50):.1f}, p95 {pct(delays, 95):.1f}, "
                 f"max {max(delays or [0]):.1f} ({len(delays)} files); "
                 f"never checked: {len(self.unchecked)} of {len(sent)}\n")
        self.verdict("upload check p95 <= 5 min", bool(delays) and pct(delays, 95) <= 300,
                     f"{pct(delays, 95):.1f} s")
        # storage: what an inspection weighs in R2, and what the owner's day costs to keep
        insp = sum(1 for r in self.rows("inspections") if self.inside(r[0]) and r[2] == "submitted")
        size = sum(s or 0 for t, s in sent.values() if self.inside(t))
        if insp and size:
            per = size / insp / 1e6
            stored_gb = per * INSPECTIONS_PER_DAY * RETENTION_DAYS / 1000
            day_gb = per * INSPECTIONS_PER_DAY / 1000
            self.say(f"- storage: about {per:.0f} MB per inspection → {day_gb:.1f}"
                     f" GB a day at 100 a day; kept {RETENTION_DAYS} days ≈ {stored_gb:.0f} GB "
                     f"≈ ${stored_gb * R2_PER_GB_MONTH:.0f} a month in R2\n")
            self.facts["mb_per_inspection"] = round(per, 1)

    def webhooks(self):
        hooks = [r for r in self.rows("webhooks") if self.inside(r[0])]
        hd = [float(r[3]) for r in hooks if len(r) > 3 and r[3]]
        kinds = Counter(r[1] for r in hooks)
        retries = sum(n - 1 for n in Counter(r[2] for r in hooks if len(r) > 2).values() if n > 1)
        self.say("## Webhooks (seconds from event to arrival)\n")
        self.say(f"- p50 {pct(hd, 50):.2f}, p95 {pct(hd, 95):.2f}, max {max(hd or [0]):.2f}; "
                 f"{len(hooks)} arrived {dict(kinds)}; retries {retries}\n")
        self.verdict("webhook p95 <= 5 s", bool(hd) and pct(hd, 95) <= 5, f"{pct(hd, 95):.2f} s")

    # ------------------------------------------------------------------ the server

    def server(self):
        at, cpu, peak = defaultdict(float), defaultdict(float), defaultdict(float)
        for t, name, c, mem in (r[:4] for r in self.rows("stats")):
            if self.inside(t):
                used = mib(mem.split("/")[0])
                at[t] += used
                cpu[t] += float(c.rstrip("%") or 0)
                peak[name] = max(peak[name], used)
        total = max(at.values() or [0])
        cv = [v / self.o.cpus for v in cpu.values()]
        self.say("## Server memory and CPU\n")
        self.say(f"- peak memory, all server containers together: {total:.0f} MiB "
                 f"(server: {self.o.memory_mb:.0f} MiB, ~300 for the system)")
        for n, v in sorted(peak.items(), key=lambda x: -x[1]):
            self.say(f"  - {n}: {v:.0f} MiB")
        self.say(f"- CPU (100% = all {self.o.cpus:g} vCPU): average "
                 f"{sum(cv) / max(len(cv), 1):.0f}%, 95th {pct(cv, 95):.0f}%")
        self.facts["memory_peak_mib"], self.facts["cpu_p95_pct"] = total, pct(cv, 95)
        self.verdict("memory fits", total <= self.o.memory_mb - 300,
                     f"{total:.0f} of {self.o.memory_mb - 300:.0f} MiB")
        # passing is not enough to choose a size: a server's CPU varies by 10-20% from day to day
        # (shared vCPUs), so the choice needs room to spare
        usable = self.o.memory_mb - 300
        room = pct(cv, 95) < 80 and total <= 0.9 * usable
        self.facts["headroom"] = room
        self.verdict("headroom (CPU p95 < 80%, memory <= 90% of usable)", room if cv else None,
                     f"CPU p95 {pct(cv, 95):.0f}%, memory {total:.0f} of {usable:.0f} MiB")

        host = [r for r in self.rows("host") if self.inside(r[0])]
        if not host:
            self.say("- (no host.csv: no swap, database or queue figures)\n")
            return
        col = lambda i: [num(r[i]) for r in host if len(r) > i and num(r[i]) is not None]  # noqa: E731
        avail, swap, load = col(2), col(3), col(4)
        if avail:
            self.say(f"- the server's own memory: least available {min(avail):.0f} MiB; "
                     f"swap used at most {max(swap or [0]):.0f} MiB; load (1 min) at most "
                     f"{max(load or [0]):.1f} for {self.o.cpus:g} vCPU")
            self.verdict("swap barely used (< 200 MiB)", max(swap or [0]) < 200,
                         f"{max(swap or [0]):.0f} MiB")
        disk, db, conns = col(5), col(6), col(7)
        if db:
            grow = (db[-1] - db[0]) / max(self.minutes / 60, 1e-9)
            self.say(f"- disk used at most {max(disk or [0]):.0f}%; database {db[0]:.0f} → "
                     f"{db[-1]:.0f} MiB (+{grow:.0f} MiB an hour at this load); connections at "
                     f"most {max(conns or [0]):.0f}")
            self.facts.update(db_mib=db[-1], db_growth_mib_hour=grow,
                              db_connections_max=max(conns or [0]))
        queues = ("default", "uploads", "notify", "pdf", "zips", "purge")
        lens = {q: [num(r[8 + i]) or 0 for r in host if len(r) > 8 + i]
                for i, q in enumerate(queues)}
        busy = {q: v for q, v in lens.items() if v and max(v) > 0}
        self.say("- work waiting in the queues (most / at the end): " + (", ".join(
            f"{q} {max(v):.0f}/{v[-1]:.0f}" for q, v in busy.items()) or "always empty"))
        growing = [q for q, v in busy.items() if v[-1] > max(5, v[0]) and v[-1] >= max(v) * 0.8]
        self.say("")
        self.verdict("work keeps up (no queue still growing at the end)", not growing,
                     ", ".join(growing) or "keeps up")

    # ------------------------------------------------------------------ zero loss

    def zero_loss(self):
        ins = self.rows("inspections")
        began = {r[1] for r in ins if r[2] == "begin"}
        submitted = {r[1] for r in ins if r[2] == "submitted"}
        failed = [r for r in ins if r[2].startswith("failed")]
        stages = {r[0]: r[1] for r in self.rows("stages")}
        not_done = [b for b in submitted if stages.get(b) != "completed"]
        self.say("## Zero loss (the whole run)\n")
        self.say(f"- inspections begun {len(began)}, submitted {len(submitted)}, failed "
                 f"{len(failed)}, submitted but not completed {len(not_done)}")
        if failed:
            self.say("- failures: " + "; ".join(r[2][:120] for r in failed[:5]))
        self.say(f"- files never checked: {len(self.unchecked)}\n")
        self.verdict("zero loss", not self.unchecked and not not_done and not failed,
                     f"{len(self.unchecked)} files unchecked, {len(not_done)} not completed, "
                     f"{len(failed)} failed")

    def generator(self):
        """A load server that ran out of CPU sends less than it should and times answers late:
        then the run says nothing about the server under test."""
        p = os.path.join(self.o.run, "locust.log")
        text = open(p).read() if os.path.exists(p) else ""
        hot = "CPU usage above" in text or "CPU usage exceeded" in text
        self.verdict("load generator kept up (its CPU never maxed out)",
                     None if not text else not hot,
                     "its CPU maxed out: rerun on a bigger load server" if hot else
                     ("ok" if text else "no locust.log"))

    def run(self):
        self.say(f"# Load test results ({self.minutes:.0f} min from minute "
                 f"{self.o.from_min:.0f}, {self.mult:g}x)\n")
        if self.cut:
            self.say(f"_The run ended before the {self.o.minutes:.0f} minutes asked: judged on "
                     f"the {self.minutes:.0f} it ran._\n")
        for part in (self.generator, self.load, self.requests, self.pdfs, self.uploads,
                     self.webhooks,
                     self.server, self.zero_loss):
            part()
        self.say("## Verdict\n\n| Check | Result | Measured |\n|---|---|---|")
        for v in self.verdicts:
            word = "N/A" if v["pass"] is None else "PASS" if v["pass"] else "FAIL"
            self.say(f"| {v['check']} | {word} | {v['measured']} |")
        ok = all(v["pass"] is not False for v in self.verdicts)
        self.say(f"\n**{'Every check passed.' if ok else 'Not every check passed.'}**")
        name = f"verdict-{self.o.step:g}x.json" if self.o.step is not None else "verdict.json"
        with open(os.path.join(self.o.run, name), "w") as f:
            json.dump({"mult": self.mult, "pass": ok, "checks": self.verdicts,
                       "facts": self.facts}, f, indent=1, default=str)
        return "\n".join(self.lines)


if __name__ == "__main__":
    print(Report(args()).run())
