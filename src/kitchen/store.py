"""SQLite persistence. One user, one file, no server to keep alive."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from . import brewing
from .provenance import Kind, Value

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
READING_KINDS = ("gravity", "temperature", "volume", "ph")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Store:
    def __init__(self, path: str | Path = "kitchen.db") -> None:
        self.path = str(path)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- recipes

    def create_recipe(
        self,
        name: str,
        style: str | None = None,
        batch_size_gal: float | None = None,
        notes: str | None = None,
        ingredients: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO recipes (name, style, batch_size_gal, notes, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, style, batch_size_gal, notes, now_iso()),
            )
            recipe_id = int(cur.lastrowid)
            for ing in ingredients or []:
                conn.execute(
                    "INSERT INTO recipe_ingredients"
                    " (recipe_id, name, category, amount, unit, use_stage,"
                    "  provenance_kind, source)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        recipe_id,
                        ing["name"],
                        ing.get("category", "fermentable"),
                        float(ing["amount"]),
                        ing["unit"],
                        ing.get("use_stage"),
                        ing.get("provenance_kind", Kind.USER_SUPPLIED.value),
                        ing.get("source"),
                    ),
                )
        return self.get_recipe(recipe_id)

    def get_recipe(self, recipe_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
            if row is None:
                raise KeyError(f"recipe {recipe_id} not found")
            ingredients = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY id",
                    (recipe_id,),
                )
            ]
        recipe = dict(row)
        recipe["ingredients"] = ingredients
        return recipe

    def list_recipes(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM recipes ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------------- batches

    def create_batch(
        self,
        code: str,
        recipe_id: int | None = None,
        name: str | None = None,
        started_at: str | None = None,
        volume_gal: float | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        status_source = Kind.USER_SUPPLIED.value if status else Kind.INFERRED.value
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO batches"
                " (recipe_id, code, name, started_at, volume_gal, status,"
                "  status_source, notes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    recipe_id,
                    code,
                    name,
                    started_at or now_iso(),
                    volume_gal,
                    status,
                    status_source,
                    notes,
                ),
            )
            batch_id = int(cur.lastrowid)
        return self.get_batch(batch_id)

    def get_batch(self, batch_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
            if row is None:
                raise KeyError(f"batch {batch_id} not found")
        return dict(row)

    def get_batch_by_code(self, code: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM batches WHERE code = ?", (code,)).fetchone()
            if row is None:
                raise KeyError(f"batch {code!r} not found")
        return dict(row)

    def list_batches(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM batches ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]

    def set_batch_status(self, batch_id: int, status: str) -> dict[str, Any]:
        """A user-stated status. Recorded as user_supplied, not as an observation."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE batches SET status = ?, status_source = ? WHERE id = ?",
                (status, Kind.USER_SUPPLIED.value, batch_id),
            )
        return self.get_batch(batch_id)

    # ---------------------------------------------------------------- readings

    def add_reading(
        self,
        batch_id: int,
        kind: str,
        amount: float,
        unit: str,
        provenance_kind: str,
        method: str | None = None,
        source: str | None = None,
        taken_at: str | None = None,
        note: str | None = None,
        supersedes_id: int | None = None,
    ) -> dict[str, Any]:
        if kind not in READING_KINDS:
            raise ValueError(f"unknown reading kind {kind!r}; expected one of {READING_KINDS}")
        if Kind(str(provenance_kind)) in (Kind.MEASURED, Kind.CALCULATED) and not method:
            raise ValueError(f"a {provenance_kind} reading needs a method")
        self.get_batch(batch_id)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO readings"
                " (batch_id, taken_at, kind, amount, unit, provenance_kind, method,"
                "  source, note, supersedes_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    batch_id,
                    taken_at or now_iso(),
                    kind,
                    float(amount),
                    unit,
                    str(provenance_kind),
                    method,
                    source,
                    note,
                    supersedes_id,
                ),
            )
            reading_id = int(cur.lastrowid)
            row = conn.execute("SELECT * FROM readings WHERE id = ?", (reading_id,)).fetchone()
        return dict(row)

    def list_readings(self, batch_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM readings WHERE batch_id = ? ORDER BY taken_at, id",
                (batch_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- transfers

    def add_transfer(
        self,
        batch_id: int,
        to_vessel: str,
        from_vessel: str | None = None,
        volume_gal: float | None = None,
        occurred_at: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        self.get_batch(batch_id)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO transfers"
                " (batch_id, occurred_at, from_vessel, to_vessel, volume_gal, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (batch_id, occurred_at or now_iso(), from_vessel, to_vessel, volume_gal, note),
            )
            row = conn.execute(
                "SELECT * FROM transfers WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
        return dict(row)

    def list_transfers(self, batch_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transfers WHERE batch_id = ? ORDER BY occurred_at, id",
                (batch_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- inventory

    def upsert_inventory(
        self,
        name: str,
        amount: float,
        unit: str = "each",
        category: str = "other",
        provenance_kind: str = Kind.USER_SUPPLIED.value,
        source: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO inventory_items"
                " (name, category, amount, unit, provenance_kind, source, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(name) DO UPDATE SET"
                "  amount = excluded.amount, unit = excluded.unit,"
                "  category = excluded.category,"
                "  provenance_kind = excluded.provenance_kind,"
                "  source = excluded.source, updated_at = excluded.updated_at",
                (name, category, float(amount), unit, provenance_kind, source, now_iso()),
            )
            row = conn.execute(
                "SELECT * FROM inventory_items WHERE name = ?", (name,)
            ).fetchone()
        return dict(row)

    def list_inventory(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inventory_items ORDER BY category, name"
            ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- purchases

    def add_purchase(
        self,
        vendor: str,
        lines: list[dict[str, Any]],
        purchased_at: str | None = None,
        invoice_no: str | None = None,
        source: str | None = None,
        currency: str = "USD",
    ) -> dict[str, Any]:
        total = 0.0
        for line in lines:
            line_total = line.get("line_total")
            if line_total is None:
                unit_price = line.get("unit_price")
                line_total = (
                    float(line["qty"]) * float(unit_price) if unit_price is not None else None
                )
            if line_total is not None:
                total += float(line_total)
            line["_line_total"] = line_total
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO purchases"
                " (vendor, purchased_at, invoice_no, total, currency, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (vendor, purchased_at or now_iso(), invoice_no, round(total, 2), currency, source),
            )
            purchase_id = int(cur.lastrowid)
            for line in lines:
                conn.execute(
                    "INSERT INTO purchase_lines"
                    " (purchase_id, inventory_item_id, description, qty, unit,"
                    "  unit_price, line_total) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        purchase_id,
                        line.get("inventory_item_id"),
                        line["description"],
                        float(line["qty"]),
                        line["unit"],
                        line.get("unit_price"),
                        line["_line_total"],
                    ),
                )
        return self.get_purchase(purchase_id)

    def get_purchase(self, purchase_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
            if row is None:
                raise KeyError(f"purchase {purchase_id} not found")
            lines = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM purchase_lines WHERE purchase_id = ? ORDER BY id",
                    (purchase_id,),
                )
            ]
        purchase = dict(row)
        purchase["lines"] = lines
        return purchase

    def list_purchases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM purchases ORDER BY purchased_at DESC").fetchall()
        return [dict(r) for r in rows]

    def spend_by_vendor(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT vendor, COUNT(*) AS purchases, ROUND(SUM(total), 2) AS total"
                " FROM purchases GROUP BY vendor ORDER BY total DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- reference

    def add_reference(
        self,
        title: str,
        body: str,
        source_url: str | None = None,
        source_title: str | None = None,
        retrieved_at: str | None = None,
        license: str | None = None,
    ) -> dict[str, Any]:
        if not source_url:
            raise ValueError("reference notes need a source_url: knowledge without a source is a rumour")
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO reference_notes"
                " (title, body, source_url, source_title, retrieved_at, license)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (title, body, source_url, source_title, retrieved_at or now_iso(), license),
            )
            row = conn.execute(
                "SELECT * FROM reference_notes WHERE id = ?", (int(cur.lastrowid),)
            ).fetchone()
        return dict(row)

    def search_reference(self, query: str) -> list[dict[str, Any]]:
        like = f"%{query}%"
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reference_notes WHERE title LIKE ? OR body LIKE ?"
                " ORDER BY id DESC",
                (like, like),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- summary

    def batch_summary(self, batch_id: int) -> dict[str, Any]:
        """Everything known about a batch, with each claim labelled."""
        batch = self.get_batch(batch_id)
        readings = self.list_readings(batch_id)
        gravities = [r for r in readings if r["kind"] == "gravity"]
        caveats: list[str] = []

        first_gravity = None
        latest_gravity = None
        abv = None
        attenuation = None

        if gravities:
            first, last = gravities[0], gravities[-1]
            first_gravity = Value(
                first["amount"], first["unit"], Kind(first["provenance_kind"]),
                method=first["method"] or "", source=first["source"] or "",
            )
            latest_gravity = Value(
                last["amount"], last["unit"], Kind(last["provenance_kind"]),
                method=last["method"] or "", source=last["source"] or "",
            )
            lag = _parse(first["taken_at"]) - _parse(batch["started_at"])
            if lag > timedelta(hours=12):
                caveats.append(
                    f"first gravity reading came {_human_delta(lag)} after the batch started; "
                    "it may already be past the true original gravity"
                )
            if len(gravities) >= 2:
                try:
                    abv = brewing.abv_estimate(first_gravity.amount, latest_gravity.amount)
                    attenuation = brewing.apparent_attenuation(
                        first_gravity.amount, latest_gravity.amount
                    )
                except ValueError as exc:
                    caveats.append(f"ABV not computed: {exc}")
            else:
                caveats.append("only one gravity reading so far; ABV needs two")
        else:
            caveats.append("no gravity readings recorded")

        status, status_reason = self._infer_status(batch, gravities)

        return {
            "batch": batch,
            "readings": readings,
            "transfers": self.list_transfers(batch_id),
            "first_gravity": first_gravity.to_dict() if first_gravity else None,
            "latest_gravity": latest_gravity.to_dict() if latest_gravity else None,
            "abv": abv.to_dict() if abv else None,
            "apparent_attenuation": attenuation.to_dict() if attenuation else None,
            "status": status,
            "caveats": caveats,
        }

    def _infer_status(
        self, batch: dict[str, Any], gravities: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], str]:
        if batch["status_source"] == Kind.USER_SUPPLIED.value and batch["status"]:
            return (
                {
                    "value": batch["status"],
                    "kind": Kind.USER_SUPPLIED.value,
                    "reason": "set by the brewer",
                },
                "set by the brewer",
            )
        if not gravities:
            return (
                {
                    "value": "unknown",
                    "kind": Kind.INFERRED.value,
                    "reason": "no gravity readings yet",
                },
                "no gravity readings yet",
            )
        last = gravities[-1]
        stable = (
            len(gravities) >= 2
            and abs(gravities[-1]["amount"] - gravities[-2]["amount"]) <= 0.001
        )
        days = (datetime.now(timezone.utc) - _parse(last["taken_at"])).days
        if stable and days >= 3:
            reason = (
                f"last two gravity readings agree within 0.001 and the newest is "
                f"{days} days old; inferred, not observed"
            )
            return ({"value": "stable, likely ready to package", "kind": Kind.INFERRED.value, "reason": reason}, reason)
        reason = "gravity is still moving or too few readings to tell; inferred, not observed"
        return ({"value": "active or unverified", "kind": Kind.INFERRED.value, "reason": reason}, reason)


def _human_delta(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 48:
        return f"{hours:.0f} hours"
    return f"{hours / 24:.0f} days"
