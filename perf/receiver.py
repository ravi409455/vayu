#!/usr/bin/env python3
"""Webhook receiver for the load tests (docs/plan-load-test.md): answers 200 at once and writes,
for every delivery, when it arrived and how long after its event (body `occurred_at`).

    python3 perf/receiver.py --port 9300 --out results/webhooks.csv

Columns: arrived (unix s), event, delivery id, delay (s). A delivery id seen twice is a retry."""
import argparse
import csv
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

args = argparse.ArgumentParser()
args.add_argument("--port", type=int, default=9300)
args.add_argument("--out", required=True)
opts = args.parse_args()
lock = threading.Lock()
out = open(opts.out, "a", newline="")   # noqa: SIM115 - open for the server's lifetime
writer = csv.writer(out)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        now = time.time()
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.end_headers()
        try:
            occurred = datetime.fromisoformat(json.loads(body)["occurred_at"]).timestamp()
        except (ValueError, KeyError, TypeError):
            occurred = None
        with lock:
            writer.writerow([f"{now:.3f}", self.headers.get("X-Vayu-Event", ""),
                             self.headers.get("X-Vayu-Delivery", ""),
                             "" if occurred is None else f"{now - occurred:.3f}"])
            out.flush()

    do_PUT = do_PATCH = do_POST

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", opts.port), Handler).serve_forever()  # noqa: S104 - test only
