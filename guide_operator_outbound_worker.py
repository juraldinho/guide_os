"""CLI entrypoint for GO8F2B Guide Operator outbound delivery worker.

Separate process only:
  python guide_operator_outbound_worker.py
  python guide_operator_outbound_worker.py --once

Never started from bot.py, Mini App API, or guide_operator_integration_api.py.
Default off; enable only via env after outbound HTTP + service-auth are complete.
"""

from __future__ import annotations

import sys

from services.guide_operator_outbound_worker import main

if __name__ == "__main__":
    sys.exit(main())
