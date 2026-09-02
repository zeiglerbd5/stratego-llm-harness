"""The Game Record: an append-only JSONL event stream, replayable from scratch.

Observations are derivable from the Deployments plus the Move list, so they are
not written by default. Rationale and native reasoning always are.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class GameRecord:
    def __init__(self, path: str | Path, meta: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.path.open("w", encoding="utf-8")
        self.write("game_start", **meta)

    def write(self, kind: str, **payload) -> None:
        rec = {"t": round(time.time(), 3), "kind": kind, **payload}
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fh.flush()

    def close(self, **payload) -> None:
        self.write("game_end", **payload)
        self.fh.close()
