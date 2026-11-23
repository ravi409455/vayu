#!/usr/bin/env python3
"""A tiny webhook receiver for trying integrations on this laptop.

    python3 scripts/webhook_receiver.py [--port 9099] [--fail]

Point an integration at http://127.0.0.1:9099/anything. Every request is printed whole: method,
path with query, headers and body (any method, any path). Answer 500 to see the retry behaviour:
--fail"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

args = argparse.ArgumentParser()
args.add_argument("--port", type=int, default=9099)
args.add_argument("--fail", action="store_true", help="answer 500 to every request")
opts = args.parse_args()


class Handler(BaseHTTPRequestHandler):
    def handle_any(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        print(f"\n--- {self.command} {self.path}", flush=True)
        for name, value in self.headers.items():
            print(f"    {name}: {value}")
        if body:
            try:
                print(json.dumps(json.loads(body), indent=2), flush=True)
            except ValueError:
                print("(not JSON) " + body[:200].decode(errors="replace"), flush=True)
        self.send_response(500 if opts.fail else 200)
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

    def log_message(self, *_):
        pass


print(f"Listening on http://127.0.0.1:{opts.port}/" + ("  (answering 500)" if opts.fail else ""))
HTTPServer(("127.0.0.1", opts.port), Handler).serve_forever()
