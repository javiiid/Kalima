"""Phase 2.1: the backend serves the built React bundle on one origin."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.storage.database import Database

INDEX_MARKER = "<title>KALIMA-shell</title>"


def _build_dist(root):
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        f"<!doctype html>{INDEX_MARKER}<script src=/assets/app.js></script>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('kalima');", encoding="utf-8")
    return dist


@pytest.fixture
def live(tmp_path, monkeypatch):
    dist = _build_dist(tmp_path)
    monkeypatch.setenv("KALIMA_UI_DIST", str(dist))
    monkeypatch.delenv("KALIMA_SERVE_SPA", raising=False)
    database = Database(tmp_path / "spa.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _get(server, path):
    connection = HTTPConnection(*server.server_address)
    connection.request("GET", path, None, {})
    response = connection.getresponse()
    body = response.read()
    headers = {name.lower(): value for name, value in response.getheaders()}
    connection.close()
    return response.status, body, headers


def test_root_serves_the_app_shell_with_security_headers(live):
    status, body, headers = _get(live, "/")
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert INDEX_MARKER in body.decode("utf-8")
    assert headers["x-content-type-options"] == "nosniff"
    assert "Content-Security-Policy" in {k.title(): v for k, v in headers.items()}
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["cache-control"] == "no-cache"


def test_deep_link_falls_back_to_the_shell(live):
    # The client router owns /library; a plain GET must still return the shell.
    status, body, headers = _get(live, "/library")
    assert status == 200 and INDEX_MARKER in body.decode("utf-8")


def test_hashed_assets_get_correct_mime_and_immutable_cache(live):
    status, body, headers = _get(live, "/assets/app.js")
    assert status == 200
    assert "javascript" in headers["content-type"]
    assert "immutable" in headers["cache-control"]
    assert body == b"console.log('kalima');"


def test_missing_asset_is_a_404_not_the_shell(live):
    status, body, _ = _get(live, "/assets/missing.js")
    assert status == 404
    assert INDEX_MARKER.encode() not in body


def test_sourcemaps_are_never_served(live, tmp_path):
    # A built bundle ships index-*.js.map; it exposes the original source and
    # must not be reachable in production.
    import os

    dist = os.environ["KALIMA_UI_DIST"]
    source_map = os.path.join(dist, "assets", "app.js.map")
    with open(source_map, "w", encoding="utf-8") as handle:
        handle.write("{}")
    status, _, _ = _get(live, "/assets/app.js.map")
    assert status == 404


def test_api_routes_still_win_over_the_spa(live):
    status, body, headers = _get(live, "/api/jobs")
    assert status == 200 and headers["content-type"].startswith("application/json")


def test_path_traversal_is_refused(live):
    status, body, _ = _get(live, "/assets/%2e%2e%2f%2e%2e%2fpyproject.toml")
    assert status == 404 and INDEX_MARKER.encode() not in body


def test_spa_can_be_disabled(tmp_path, monkeypatch):
    dist = _build_dist(tmp_path)
    monkeypatch.setenv("KALIMA_UI_DIST", str(dist))
    monkeypatch.setenv("KALIMA_SERVE_SPA", "0")
    database = Database(tmp_path / "off.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, _, _ = _get(server, "/library")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
