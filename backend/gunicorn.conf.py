"""Gunicorn in production (F-074 / F-211): the access log never holds search terms (no query
string) or the report / ZIP tokens in a path (they are links that open customer files)."""
import os
import re

from gunicorn.glogging import Logger

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))   # a 4 GB box; on 8 GB: 4
accesslog = "-"
access_log_format = '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(B)s %(L)s'
TOKEN = re.compile(r"/(verify|zips|zip)/[^/]+")


class SafeLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        atoms["U"] = TOKEN.sub(r"/\1/<token>", atoms.get("U", ""))
        return atoms


logger_class = SafeLogger
