"""Eksport til Form & Fokus-siden.

    python -m garmin_coach.export maaneder [MAPPE] [--versioner JSON]

Skriver én JSON-fil pr. måned (samling "maaneder", id 'ÅÅÅÅ-MM') og
oversigt.json (samling "oversigt", id "seneste") og udskriver de
ArtifactData-batch-skrivninger der lægger dem på siden. Skrivningerne peger
på filerne med file_path, så tallene aldrig skal skrives af i hånden.

ArtifactData afviser at overskrive et eksisterende dokument uden if_version.
--versioner tager de versioner siden har nu, som JSON med nøglen
"samling/id", fx '{"maaneder/2026-09": 2, "oversigt/seneste": 2}'.
Dokumenter der ikke står der, skrives som nye.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .db import connect
from .metrics import maanedsoversigt

DEFAULT_DIR = Path.home() / ".garmin-coach" / "export"
BATCH_SIZE = 50  # ArtifactData tager højst 50 skrivninger pr. batch


def export_maaneder(
    conn: sqlite3.Connection, out_dir: Path = DEFAULT_DIR,
    versioner: dict[str, int] | None = None,
) -> list[list[dict]]:
    """Skriv filerne og returnér batch-skrivningerne i bidder på højst 50.

    versioner ("samling/id" → version) sætter if_version på de dokumenter
    der allerede findes på siden."""
    ov = maanedsoversigt(conn)
    genereret = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    month_dir = out_dir / "maaneder"
    month_dir.mkdir(parents=True, exist_ok=True)

    writes = []
    for row in ov["maaneder"]:
        path = month_dir / f"{row['maaned']}.json"
        path.write_text(json.dumps({**row, "genereret": genereret}, ensure_ascii=False))
        writes.append({"op": "set", "collection": "maaneder",
                       "doc_id": row["maaned"], "file_path": str(path)})

    months = [r["maaned"] for r in ov["maaneder"]]
    path = out_dir / "oversigt.json"
    path.write_text(json.dumps({
        "udvikling": ov["udvikling"],
        "forbehold": ov["forbehold"],
        "fra": months[0] if months else None,
        "til": months[-1] if months else None,
        "genereret": genereret,
    }, ensure_ascii=False))
    writes.append({"op": "set", "collection": "oversigt", "doc_id": "seneste",
                   "file_path": str(path)})
    for w in writes:
        version = (versioner or {}).get(f"{w['collection']}/{w['doc_id']}")
        if version is not None:
            w["if_version"] = int(version)
    return [writes[i:i + BATCH_SIZE] for i in range(0, len(writes), BATCH_SIZE)]


def _cli() -> None:
    args = sys.argv[1:]
    versioner = None
    if "--versioner" in args:
        i = args.index("--versioner")
        if i + 1 >= len(args):
            sys.exit(__doc__)
        versioner = json.loads(args[i + 1])
        del args[i:i + 2]
    if not args or args[0] != "maaneder":
        sys.exit(__doc__)
    out_dir = Path(args[1]).expanduser() if len(args) > 1 else DEFAULT_DIR
    conn = connect()
    try:
        batches = export_maaneder(conn, out_dir, versioner)
    finally:
        conn.close()
    print(json.dumps({"batches": batches}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _cli()
