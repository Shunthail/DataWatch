import queue
import threading
from datetime import datetime, timezone
from http.client import HTTPException

from backend import storage
from backend.detection import detect, mask
from backend.feeds import fetch_text, parse_entries


def scan_source(identifier):
    source = next(
        (item for item in storage.list_rows("sources") if item["id"] == identifier),
        None,
    )
    if not source:
        raise LookupError("Source introuvable.")
    if not source["enabled"]:
        return {"entries": 0, "alerts": 0, "skipped": True}
    storage.start_scan(identifier)
    try:
        entries = parse_entries(
            fetch_text(source["url"]), source["format"], source["url"]
        )
        alerts = detect(source, entries, storage.list_rows("rules"))
        count = storage.finish_scan(identifier, source["name"], len(entries), alerts)
        return {"entries": len(entries), "alerts": count}
    except (ValueError, OSError, HTTPException) as error:
        message = mask(str(error))[:300]
        storage.finish_scan(identifier, source["name"], 0, [], message)
        return {"entries": 0, "alerts": 0, "error": message}
    except Exception:
        storage.finish_scan(
            identifier,
            source["name"],
            0,
            [],
            "Impossible de lire cette source. Vérifiez son format.",
        )
        return {
            "entries": 0,
            "alerts": 0,
            "error": "Format de source non pris en charge.",
        }


class Collector:
    def __init__(self, interval=300):
        self.interval = interval
        self.pending = queue.Queue()
        self.scheduled = set()
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self.run, name="source-collector", daemon=True
        )

    def enqueue(self, identifier):
        with self.lock:
            if identifier in self.scheduled:
                return False
            self.scheduled.add(identifier)
            self.pending.put(identifier)
            return True

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=10)

    def run(self):
        while not self.stopped.is_set():
            for source in storage.list_rows("sources"):
                last = (
                    datetime.fromisoformat(source["last_checked"])
                    if source["last_checked"]
                    else None
                )
                if source["enabled"] and (
                    last is None
                    or (datetime.now(timezone.utc) - last).total_seconds()
                    >= self.interval
                ):
                    self.enqueue(source["id"])
            try:
                identifier = self.pending.get(timeout=1)
            except queue.Empty:
                continue
            try:
                scan_source(identifier)
            except LookupError:
                pass
            finally:
                with self.lock:
                    self.scheduled.discard(identifier)
                self.pending.task_done()
