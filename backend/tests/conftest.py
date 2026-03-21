"""Test bootstrap for backend smoke tests.

Pytest can collect these tests without putting the backend root on ``sys.path``
reliably across environments. The tests import local modules like ``config``
and ``main`` directly, so we prepend the backend directory explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
