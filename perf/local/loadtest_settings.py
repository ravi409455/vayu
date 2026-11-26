"""Local load test only (perf/local): production settings, except that webhooks may go to the
receiver on this laptop (plain http, a private address). Mounted into the containers by
perf/local/compose.yml; it is not part of any image."""
from .prod import *  # noqa: F401,F403

WEBHOOK_ALLOW_HTTP = True
WEBHOOK_ALLOW_PRIVATE = True
