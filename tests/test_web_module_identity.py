"""The web server must expose exactly one module instance.

``python -m app.web`` executes ``app/web.py`` as ``__main__`` and does not
register it under ``app.web``. The calibration routes do ``from app import
web``, which then imported a *second* copy of the module with its own
``JOBS`` dict, its own scheduler and its own ``Job`` class. Starting a
calibrated book registered the job in that copy, so the running server's
monitor answered 404 -- "this job was not found" -- the moment the user asked
for the translation.
"""
from __future__ import annotations

import sys
import types


def test_running_as_main_publishes_the_module_under_its_canonical_name():
    import app.web as web

    fake_main = types.ModuleType("__main__")
    fake_main.JOBS = {}
    saved_main = sys.modules.get("__main__")
    saved_canonical = sys.modules.get("app.web")
    try:
        sys.modules["__main__"] = fake_main
        sys.modules.pop("app.web", None)

        web._publish_as_canonical_module("__main__")

        assert sys.modules["app.web"] is fake_main
        assert getattr(sys.modules["app"], "web") is fake_main
        # The very thing the calibration routes do.
        from app import web as imported
        assert imported is fake_main
        assert imported.JOBS is fake_main.JOBS
    finally:
        if saved_canonical is not None:
            sys.modules["app.web"] = saved_canonical
            setattr(sys.modules["app"], "web", saved_canonical)
        if saved_main is not None:
            sys.modules["__main__"] = saved_main


def test_a_normal_import_is_left_alone():
    import app.web as web

    before = sys.modules.get("app.web")
    web._publish_as_canonical_module()
    assert sys.modules["app.web"] is before is web
