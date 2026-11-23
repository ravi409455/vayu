#!/usr/bin/env python3
"""A tiny webhook receiver for trying integrations on this laptop.

    python3 scripts/webhook_receiver.py [--port 9099] [--secret whsec_...]

Point an integration at http://127.0.0.1:9099/hook. Every delivery is printed with the event,
the booking, and whether the HMAC signature is valid (pass the integration's secret to check it).
Answer 500 to see the retry behaviour:  --fail"""
import argparse
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

args = argparse.ArgumentParser()
args.add_argument("--port", type=int, default=9099)
args.add_argument("--secret", default="")
args.add_argument("--fail", action="store_true", help="answer 500 to every delivery")
opts = args.parse_args()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        got = self.headers.get("X-Vayu-Signature", "")
        if opts.secret:
            want = "sha256=" + hmac.new(opts.secret.encode(), body, hashlib.sha256).hexdigest()
            verdict = "signature OK" if hmac.compare_digest(got, want) else "SIGNATURE WRONG"
        else:
            verdict = "signature not checked (no --secret)"
        try:
            data = json.loads(body)
            what = f"{data.get('event')}  booking {data.get('booking', {}).get('booking_id')}"
            keys = sorted(data)
        except ValueError:
            what, keys = "(not JSON) " + body[:80].decode(errors="replace"), []
        print(f"\n--- {self.headers.get('X-Vayu-Event')}  {what}\n    {verdict}; fields: {keys}",
              flush=True)
        self.send_response(500 if opts.fail else 200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):
        pass


print(f"Listening on http://127.0.0.1:{opts.port}/hook" + ("  (answering 500)" if opts.fail else ""))
HTTPServer(("127.0.0.1", opts.port), Handler).serve_forever()
