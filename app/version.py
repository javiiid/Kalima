"""Single source of truth for the running build's version.

``pyproject.toml`` reads this back through setuptools' ``dynamic`` version, so
there is exactly one place to bump. It is a plain constant rather than
``importlib.metadata`` on purpose: an editable install's ``.egg-info`` keeps
the version it was installed with, so reading metadata there would report a
stale value to ``/api/version`` after every bump.
"""

from __future__ import annotations

import os

#: Bump on release. ``KALIMA_VERSION`` overrides it in a build pipeline that
#: wants to stamp a CI value without editing source.
__version__ = "0.2.0"
APP_NAME = "kalima"


def get_version() -> str:
    return (os.environ.get("KALIMA_VERSION") or "").strip() or __version__
