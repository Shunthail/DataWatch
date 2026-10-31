import json
import mimetypes
import re
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from backend import storage
from backend.detection import EMAIL
from backend.feeds import validate_url
from backend.scanner import Collector

FRONTEND = (
    Path(__file__).resolve().parents[1] / "frontend" / "dist" / "datawatch" / "browser"
)
ORIGINS = {
    "http://127.0.0.1:4210",
    "http://localhost:4210",
    "http://127.0.0.1:8010",
    "http://localhost:8010",
}


def text(payload, key, limit):
    value = payload.get(key)
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f"Champ {key} requis, de 1 à {limit} caractères.")
    return value.strip()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/api/health":
            return self.send_json(200, {"status": "ok"})
        if path == "/api/state":
            return self.send_json(200, storage.state())
        if path == "/api/events":
            return self.events()
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Route introuvable."})
        requested = (FRONTEND / path.lstrip("/")).resolve()
        if not requested.is_relative_to(FRONTEND.resolve()):
            return self.send_json(403, {"error": "Accès refusé."})
        if not requested.is_file():
            if requested.suffix:
                return self.send_json(404, {"error": "Fichier introuvable."})
            requested = FRONTEND / "index.html"
        if not requested.exists():
            return self.send_json(
                503, {"error": "Compiler le frontend avec bash scripts/build.sh."}
            )
        body = requested.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(str(requested))[0] or "application/octet-stream",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        previous = None
        try:
            while not self.server.stopped.is_set():
                activity = storage.list_rows("activity")
                revision = activity[0]["id"] if activity else 0
                if revision != previous:
                    self.wfile.write(f"event: update\ndata: {revision}\n\n".encode())
                    previous = revision
                else:
                    self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                self.server.stopped.wait(2)
        except OSError:
            pass

    def read_payload(self):
        if self.headers.get("Origin") and self.headers["Origin"] not in ORIGINS:
            raise PermissionError("Origine refusée.")
        if (
            self.headers.get("Content-Type", "").split(";")[0].strip()
            != "application/json"
        ):
            raise ValueError("Le corps doit être du JSON.")
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 16_384:
            raise ValueError("Requête vide ou trop volumineuse.")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("Un objet JSON est attendu.")
        return payload

    def do_POST(self):
        self.mutate("POST")

    def do_PATCH(self):
        self.mutate("PATCH")

    def mutate(self, method):
        try:
            payload = self.read_payload()
            path = urlsplit(self.path).path
            if method == "POST" and path == "/api/sources":
                name, url, format = (
                    text(payload, "name", 80),
                    validate_url(text(payload, "url", 1500)),
                    text(payload, "format", 10),
                )
                if format not in ("rss", "json", "text"):
                    raise ValueError("Formats acceptés : rss, json, text.")
                identifier = storage.add_source(name, url, format)
                self.server.collector.enqueue(identifier)
                return self.send_json(201, storage.state())
            if method == "POST" and path == "/api/rules":
                label, kind, value, severity = (
                    text(payload, key, limit)
                    for key, limit in [
                        ("label", 80),
                        ("kind", 10),
                        ("value", 150),
                        ("severity", 10),
                    ]
                )
                if kind not in ("keyword", "email", "domain") or severity not in (
                    "low",
                    "medium",
                    "high",
                    "critical",
                ):
                    raise ValueError("Type ou sévérité de règle invalide.")
                if kind == "email" and EMAIL.fullmatch(value) is None:
                    raise ValueError("Indiquer une adresse e-mail complète.")
                if kind == "domain":
                    value = value.lower().encode("idna").decode("ascii")
                    if not re.fullmatch(
                        r"(?=.{3,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",
                        value,
                    ):
                        raise ValueError(
                            "Indiquer un domaine sans protocole ni chemin."
                        )
                storage.add_rule(label, kind, value, severity)
                return self.send_json(201, storage.state())
            if method == "POST" and path == "/api/scan":
                identifier = payload.get("sourceId")
                if identifier is not None and (
                    type(identifier) is not int or identifier < 1
                ):
                    raise ValueError("Identifiant de source invalide.")
                sources = [
                    item
                    for item in storage.list_rows("sources")
                    if item["enabled"]
                    and (identifier is None or item["id"] == identifier)
                ]
                if identifier is not None and not sources:
                    raise LookupError("Source active introuvable.")
                queued = sum(
                    self.server.collector.enqueue(source["id"]) for source in sources
                )
                return self.send_json(202, {"queued": queued})
            match = re.fullmatch(r"/api/(sources|rules|alerts)/(\d+)", path)
            if method == "PATCH" and match:
                table, identifier = match.group(1), int(match.group(2))
                if table == "alerts":
                    status = payload.get("status")
                    if status not in ("new", "reviewing", "resolved"):
                        raise ValueError("Statut invalide.")
                    storage.set_alert_status(identifier, status)
                else:
                    enabled = payload.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("Le champ enabled doit être un booléen.")
                    storage.set_enabled(table, identifier, enabled)
                return self.send_json(200, storage.state())
            self.send_json(404, {"error": "Route introuvable."})
        except PermissionError as error:
            self.send_json(403, {"error": str(error)})
        except LookupError as error:
            self.send_json(404, {"error": str(error)})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "Cette source ou cette règle existe déjà."})
        except (ValueError, TypeError, UnicodeError) as error:
            self.send_json(400, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "Impossible de traiter la requête."})


def main():
    storage.initialize()
    collector = Collector()
    with ThreadingHTTPServer(("127.0.0.1", 8010), Handler) as server:
        server.collector = collector
        server.stopped = threading.Event()
        collector.start()
        print("DataWatch → http://127.0.0.1:8010", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.stopped.set()
            collector.stop()


if __name__ == "__main__":
    main()
