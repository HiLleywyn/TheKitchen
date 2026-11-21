"""HTTP surface. FastAPI, one user, no auth (bind it to localhost)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import brewing, tools
from .provenance import Kind
from .store import Store

STATIC_DIR = Path(__file__).with_name("static")


_STORE: Store | None = None


def _store() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store(os.environ.get("KITCHEN_DB", "kitchen.db"))
    return _STORE


app = FastAPI(title="TheKitchen", version="0.1.0", description="Brewing records with provenance.")


# ------------------------------------------------------------------- payloads


class IngredientIn(BaseModel):
    name: str
    amount: float
    unit: str
    category: str = "fermentable"
    use_stage: str | None = None
    source: str | None = None


class RecipeIn(BaseModel):
    name: str
    style: str | None = None
    batch_size_gal: float | None = None
    notes: str | None = None
    ingredients: list[IngredientIn] = Field(default_factory=list)


class BatchIn(BaseModel):
    code: str
    recipe_id: int | None = None
    name: str | None = None
    volume_gal: float | None = None
    notes: str | None = None


class ReadingIn(BaseModel):
    kind: Literal["gravity", "temperature", "volume", "ph"]
    amount: float
    unit: str
    provenance_kind: Literal["measured", "calculated", "user_supplied", "estimated"] = "measured"
    method: str | None = None
    source: str | None = None
    taken_at: str | None = None
    note: str | None = None


class HydrometerIn(BaseModel):
    sg: float
    temp_f: float
    cal_temp_f: float = 60.0
    taken_at: str | None = None
    note: str | None = None


class TransferIn(BaseModel):
    to_vessel: str
    from_vessel: str | None = None
    volume_gal: float | None = None
    occurred_at: str | None = None
    note: str | None = None


class InventoryIn(BaseModel):
    name: str
    amount: float
    unit: str = "each"
    category: str = "other"
    source: str | None = None


class PurchaseLineIn(BaseModel):
    description: str
    qty: float
    unit: str
    unit_price: float | None = None
    line_total: float | None = None
    inventory_item_id: int | None = None


class PurchaseIn(BaseModel):
    vendor: str
    lines: list[PurchaseLineIn]
    purchased_at: str | None = None
    invoice_no: str | None = None
    source: str | None = None


class ReferenceIn(BaseModel):
    title: str
    body: str
    source_url: str
    source_title: str | None = None
    license: str | None = None


class ToolCallIn(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------- pages


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": os.environ.get("KITCHEN_DB", "kitchen.db")}


# -------------------------------------------------------------------- recipes


@app.get("/api/recipes")
def list_recipes() -> list[dict[str, Any]]:
    return _store().list_recipes()


@app.post("/api/recipes", status_code=201)
def create_recipe(payload: RecipeIn) -> dict[str, Any]:
    return _store().create_recipe(
        name=payload.name,
        style=payload.style,
        batch_size_gal=payload.batch_size_gal,
        notes=payload.notes,
        ingredients=[i.model_dump() for i in payload.ingredients],
    )


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: int) -> dict[str, Any]:
    try:
        return _store().get_recipe(recipe_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -------------------------------------------------------------------- batches


@app.get("/api/batches")
def list_batches() -> list[dict[str, Any]]:
    return _store().list_batches()


@app.post("/api/batches", status_code=201)
def create_batch(payload: BatchIn) -> dict[str, Any]:
    try:
        return _store().create_batch(**payload.model_dump())
    except Exception as exc:  # sqlite integrity, e.g. duplicate code
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/batches/{batch_id}")
def batch_summary(batch_id: int) -> dict[str, Any]:
    try:
        return _store().batch_summary(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/batches/{batch_id}/readings", status_code=201)
def add_reading(batch_id: int, payload: ReadingIn) -> dict[str, Any]:
    try:
        return _store().add_reading(batch_id=batch_id, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/batches/{batch_id}/gravity", status_code=201)
def add_hydrometer_reading(batch_id: int, payload: HydrometerIn) -> dict[str, Any]:
    """Record a hydrometer reading, correcting for sample temperature."""
    value = brewing.hydrometer_reading(
        payload.sg, payload.temp_f, payload.cal_temp_f, note=payload.note or ""
    )
    try:
        return _store().add_reading(
            batch_id=batch_id,
            kind="gravity",
            amount=round(value.amount, 4),
            unit="SG",
            provenance_kind=Kind.MEASURED.value,
            method=value.method,
            taken_at=payload.taken_at,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/batches/{batch_id}/transfers", status_code=201)
def add_transfer(batch_id: int, payload: TransferIn) -> dict[str, Any]:
    try:
        return _store().add_transfer(batch_id=batch_id, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/batches/{batch_id}/transfers")
def list_transfers(batch_id: int) -> list[dict[str, Any]]:
    return _store().list_transfers(batch_id)


# ------------------------------------------------------------------ inventory


@app.get("/api/inventory")
def list_inventory() -> list[dict[str, Any]]:
    return _store().list_inventory()


@app.post("/api/inventory", status_code=201)
def upsert_inventory(payload: InventoryIn) -> dict[str, Any]:
    return _store().upsert_inventory(**payload.model_dump())


# ------------------------------------------------------------------ purchases


@app.get("/api/purchases")
def list_purchases() -> list[dict[str, Any]]:
    return _store().list_purchases()


@app.post("/api/purchases", status_code=201)
def create_purchase(payload: PurchaseIn) -> dict[str, Any]:
    return _store().add_purchase(
        vendor=payload.vendor,
        lines=[line.model_dump() for line in payload.lines],
        purchased_at=payload.purchased_at,
        invoice_no=payload.invoice_no,
        source=payload.source,
    )


@app.get("/api/spend")
def spend() -> list[dict[str, Any]]:
    return _store().spend_by_vendor()


# ------------------------------------------------------------------ reference


@app.post("/api/reference", status_code=201)
def add_reference(payload: ReferenceIn) -> dict[str, Any]:
    try:
        return _store().add_reference(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reference")
def search_reference(q: str) -> list[dict[str, Any]]:
    return _store().search_reference(q)


# ------------------------------------------------------------------ assistant


@app.get("/api/tools")
def tool_specs() -> list[dict[str, Any]]:
    return tools.TOOL_SPECS


@app.post("/api/tools/run")
def run_tool(payload: ToolCallIn) -> dict[str, Any]:
    result = tools.run_tool(_store(), payload.tool, payload.args)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "tool failed"))
    return result
