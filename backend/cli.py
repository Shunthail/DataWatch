import argparse
import json

from backend import storage
from backend.scanner import scan_source


def main():
    parser = argparse.ArgumentParser(
        description="Collecter les sources publiques configurées dans DataWatch."
    )
    parser.add_argument(
        "--source",
        type=int,
        help="Identifiant d’une source. Toutes les sources actives par défaut.",
    )
    args = parser.parse_args()
    storage.initialize()
    sources = [
        source
        for source in storage.list_rows("sources")
        if source["enabled"] and (args.source is None or source["id"] == args.source)
    ]
    if args.source is not None and not sources:
        parser.error("Source active introuvable.")
    results = [
        dict(source=source["name"], **scan_source(source["id"])) for source in sources
    ]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 1 if any("error" in result for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
