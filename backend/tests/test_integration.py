import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import storage
from backend.scanner import Collector, scan_source
from backend.server import Handler


class PublicFeed(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.end_headers()
            return
        content = json.dumps(
            {
                "items": [
                    {
                        "id": "one",
                        "title": "Contact Acme",
                        "text": "Contact alice@acme.test ; password=sample-secret-123",
                        "url": "https://forum.example.org/posts/one",
                    }
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed = ThreadingHTTPServer(("127.0.0.1", 0), PublicFeed)
        cls.api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.api.collector = Collector()
        cls.api.stopped = threading.Event()
        cls.threads = []
        for server in (cls.feed, cls.api):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        cls.api.stopped.set()
        for server in (cls.feed, cls.api):
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = patch.object(
            storage, "DATABASE", Path(self.folder.name) / "datawatch.sqlite3"
        )
        self.database.start()
        self.addCleanup(self.database.stop)
        storage.initialize()
        self.source = storage.add_source(
            "Forum", f"http://public-feed.test:{self.feed.server_port}/feed", "json"
        )
        storage.add_rule("Entreprise", "domain", "acme.test", "medium")

    def request(self, method, path, payload=None, origin=None):
        connection = HTTPConnection(*self.api.server_address, timeout=4)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        connection.request(
            method, path, json.dumps(payload) if payload is not None else None, headers
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    @patch("backend.feeds.resolve_public", return_value="127.0.0.1")
    def test_fetch_detect_mask_persist_and_deduplicate(self, resolve):
        first = scan_source(self.source)
        self.assertEqual(first["entries"], 1)
        self.assertEqual(first["alerts"], 1)
        status, state = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        alert = state["alerts"][0]
        self.assertEqual(alert["severity"], "high")
        self.assertNotIn("sample-secret-123", json.dumps(state))
        self.assertNotIn("alice@acme.test", json.dumps(state))
        self.assertEqual(state["sources"][0]["last_status"], "ok")
        self.assertEqual(scan_source(self.source)["alerts"], 0)
        self.assertEqual(len(storage.list_rows("alerts")), 1)
        status, state = self.request(
            "PATCH", f"/api/alerts/{alert['id']}", {"status": "resolved"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["alerts"][0]["status"], "resolved")
        scan_source(self.source)
        self.assertEqual(storage.list_rows("alerts")[0]["status"], "resolved")

    def test_source_failure_is_saved_without_leaking_content(self):
        with patch(
            "backend.scanner.fetch_text", side_effect=OSError("connection refused")
        ):
            result = scan_source(self.source)
        self.assertIn("error", result)
        self.assertEqual(storage.list_rows("sources")[0]["last_status"], "error")
        self.assertEqual(storage.list_rows("alerts"), [])

    def test_disabled_source_is_not_fetched(self):
        storage.set_enabled("sources", self.source, False)
        with patch("backend.scanner.fetch_text") as fetch:
            self.assertTrue(scan_source(self.source)["skipped"])
            fetch.assert_not_called()

    def test_foreign_origin_and_bad_payload(self):
        self.assertEqual(
            self.request("POST", "/api/scan", {}, "https://other.example")[0], 403
        )
        self.assertEqual(self.request("POST", "/api/scan", [])[0], 400)
        self.assertEqual(
            self.request(
                "POST",
                "/api/rules",
                {
                    "label": "Bad",
                    "kind": "email",
                    "value": "not-email",
                    "severity": "high",
                },
            )[0],
            400,
        )

    def test_duplicates_and_mutations(self):
        self.assertEqual(
            self.request(
                "POST",
                "/api/rules",
                {
                    "label": "Another",
                    "kind": "domain",
                    "value": "acme.test",
                    "severity": "low",
                },
            )[0],
            409,
        )
        status, state = self.request(
            "PATCH", f"/api/sources/{self.source}", {"enabled": False}
        )
        self.assertEqual(status, 200)
        self.assertFalse(state["sources"][0]["enabled"])
        self.assertEqual(
            self.request("PATCH", "/api/rules/999", {"enabled": True})[0], 404
        )
        self.assertEqual(
            self.request("PATCH", "/api/alerts/999", {"status": "invalid"})[0], 400
        )

    def test_health_and_static_traversal(self):
        self.assertEqual(self.request("GET", "/api/health"), (200, {"status": "ok"}))
        self.assertEqual(self.request("GET", "/%2e%2e/%2e%2e/server.py")[0], 403)

    def test_event_stream_announces_database_changes(self):
        connection = HTTPConnection(*self.api.server_address, timeout=4)
        connection.request("GET", "/api/events")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(response.readline(), b"event: update\n")
        self.assertTrue(response.readline().startswith(b"data: "))
        connection.close()

    def test_queue_does_not_schedule_same_source_twice(self):
        collector = Collector()
        self.assertTrue(collector.enqueue(self.source))
        self.assertFalse(collector.enqueue(self.source))

    def test_creating_sources_and_rules_through_api(self):
        status, state = self.request(
            "POST",
            "/api/sources",
            {
                "name": "Another feed",
                "url": "https://public.example.org/rss",
                "format": "rss",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(state["sources"]), 2)
        self.assertEqual(state["sources"][0]["last_status"], "idle")
        status, state = self.request(
            "POST",
            "/api/rules",
            {
                "label": "Organisation",
                "kind": "keyword",
                "value": "DataWatch",
                "severity": "low",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(state["rules"]), 2)

    def test_redirect_to_private_address_is_rejected(self):
        from backend.feeds import fetch_text

        def resolve(host):
            if host == "public-feed.test":
                return "127.0.0.1"
            raise ValueError("Adresse privée refusée.")

        with patch(
            "backend.feeds.resolve_public", side_effect=resolve
        ), self.assertRaises(ValueError):
            fetch_text(f"http://public-feed.test:{self.feed.server_port}/redirect")

    @patch("backend.feeds.resolve_public", return_value="127.0.0.1")
    def test_background_collector_fetches_sources_automatically(self, resolve):
        import time

        collector = Collector(interval=60)
        collector.start()
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not storage.list_rows("alerts"):
                time.sleep(0.03)
            self.assertEqual(len(storage.list_rows("alerts")), 1)
            self.assertEqual(storage.list_rows("sources")[0]["last_status"], "ok")
        finally:
            collector.stop()

    @patch("backend.feeds.resolve_public", return_value="127.0.0.1")
    def test_cli_collects_without_running_the_web_server(self, resolve):
        import contextlib
        import io
        from backend.cli import main

        output = io.StringIO()
        with patch(
            "sys.argv", ["scan", "--source", str(self.source)]
        ), contextlib.redirect_stdout(output):
            result = main()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())[0]["alerts"], 1)
        self.assertNotIn("sample-secret-123", output.getvalue())
