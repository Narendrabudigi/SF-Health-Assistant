"""A small in-memory stand-in for the Supabase client: just the calls the dashboard code uses
(insert, upsert, update, select with eq / in_ / gt / order / limit)."""
from __future__ import annotations

from typing import Any


class _Result:
    def __init__(self, data: Any):
        self.data = data


class _Query:
    def __init__(self, db: "FakeDb", table: str):
        self._db, self._table = db, table
        self._op, self._payload, self._columns = "select", None, None
        self._filters: list[Any] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._on_conflict = "id"

    def select(self, columns: str = "*") -> "_Query":
        self._op, self._columns = "select", None if columns == "*" else columns.split(",")
        return self

    def insert(self, row: dict[str, Any]) -> "_Query":
        self._op, self._payload = "insert", row
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str = "id") -> "_Query":
        self._op, self._payload, self._on_conflict = "upsert", row, on_conflict
        return self

    def update(self, patch: dict[str, Any]) -> "_Query":
        self._op, self._payload = "update", patch
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column: str, values: list[Any]) -> "_Query":
        self._filters.append(lambda r: r.get(column) in values)
        return self

    def gt(self, column: str, value: Any) -> "_Query":
        self._filters.append(lambda r: r.get(column) is not None and r.get(column) > value)
        return self

    def order(self, column: str, desc: bool = False) -> "_Query":
        self._order = (column, desc)
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def execute(self) -> _Result:
        db = self._db
        db.calls.append((self._op, self._table))
        if db.fail:
            raise RuntimeError(db.fail)
        rows = db.tables.setdefault(self._table, [])
        if self._op == "insert":
            row = dict(self._payload)
            if self._table == "sf_dashboard_events":
                db.next_event_id += 1
                row["id"] = db.next_event_id
            rows.append(row)
            return _Result([row])
        if self._op == "upsert":
            for r in rows:
                if r.get(self._on_conflict) == self._payload.get(self._on_conflict):
                    r.update(self._payload)
                    return _Result([r])
            rows.append(dict(self._payload))
            return _Result([self._payload])
        matched = [r for r in rows if all(f(r) for f in self._filters)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload)
            return _Result(matched)
        if self._order:
            column, desc = self._order
            matched = sorted(matched, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._columns:
            matched = [{c: r.get(c) for c in self._columns} for r in matched]
        return _Result([dict(r) for r in matched])


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_event_id = 0
        self.fail: str | None = None

    def table(self, name: str) -> _Query:
        return _Query(self, name)
