"""Read-only shop connections for the router, taken from the ingestion layer (src.ingestion.BusinessDB).

BusinessDB builds the rulebook views once per shop and caches them on disk (DATAMATE_CACHE_DIR), so the agent,
which opens the same shop through its own BusinessDB, gets a cache hit instead of a second ingestion.
Keeps at most `max_open` shops open, like the agent."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..ingestion import BusinessDB


class ConnectionProvider:
    def __init__(self, root: Path | str, max_open: int = 2):
        self.root = Path(root)
        self.max_open = max_open
        self._open: dict[str, BusinessDB] = {}
        cal = self.root / "calendar.csv"
        self._calendar = cal if cal.is_file() else None

    def connection(self, shop: str) -> sqlite3.Connection:
        base = (self.root / "data").resolve()
        target = (base / str(shop)).resolve()
        if target.parent != base:  # same guard as the agent: only directories directly under <root>/data
            raise ValueError(f"Invalid shop id: {shop!r}")
        if shop not in self._open:
            if len(self._open) >= self.max_open:
                self._open.pop(next(iter(self._open))).close()
            self._open[shop] = BusinessDB(target, self._calendar)
        return self._open[shop].connection

    def close(self) -> None:
        for db in self._open.values():
            db.close()
        self._open.clear()
