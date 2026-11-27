"""Gunicorn in production (F-074 / F-211): the access log never holds search terms (no query
string) or the report / ZIP tokens in a path (they are links that open customer files)."""
import os
import re

from gunicorn.glogging import Logger

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))   # a 4 GB box; on 8 GB: 4
# each worker answers 4 requests at a time: a request waiting for R2 (a photo's upload start or
# finish) no longer holds up Today or search. Catch: a template preview (draws a whole PDF, up to
# ~45 s of CPU) slows the other requests of its own worker while it runs
threads = int(os.environ.get("WEB_THREADS", "4"))
# a request may run 2 minutes, not gunicorn's 30 s: a template preview draws the whole PDF in the
# request (on staging's 2 vCPU about 45 s for a full PDI); past 30 s gunicorn killed the worker
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
accesslog = "-"
access_log_format = '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(B)s %(L)s'
TOKEN = re.compile(r"/(verify|zips|zip)/[^/]+")


class SafeLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        # "U" can be None (a request cut off before its path was read): never crash the log line
        atoms["U"] = TOKEN.sub(r"/\1/<token>", atoms.get("U") or "")
        return atoms


logger_class = SafeLogger
