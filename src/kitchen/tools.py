"""Deterministic tools the assistant is allowed to call.

The assistant layer is deliberately model-agnostic: these functions are the
whole surface. Whatever LLM is wired in later gets this list and nothing else,
so every number it reports came from a calculation or a stored reading rather
than from the model's memory of what beer usually does.
"""

from __future__ import annotations

from typing import Any, Callable

from . import brewing
from .provenance import Kind
from .store import Store

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "estimate_abv",
        "description": (
            "Estimate ABV from two measured gravities. Returns an ESTIMATED value, "
            "never a measurement."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "og": {"type": "number", "description": "original gravity, e.g. 1.052"},
                "fg": {"type": "number", "description": "final gravity, e.g. 1.011"},
                "method": {"type": "string", "enum": list(brewing.ABV_METHODS)},
            },
            "required": ["og", "fg"],
        },
    },
    {
        "name": "correct_hydrometer",
        "description": "Temperature-correct a hydrometer reading to 60 F.",
        "parameters": {
            "type": "object",
            "properties": {
                "sg": {"type": "number"},
                "temp_f": {"type": "number"},
                "cal_temp_f": {"type": "number"},
            },
            "required": ["sg", "temp_f"],
        },
    },
    {
        "name": "convert_gravity",
        "description": "Convert between specific gravity and degrees Plato.",
        "parameters": {
            "type": "object",
            "properties": {
                "sg": {"type": "number"},
                "plato": {"type": "number"},
            },
        },
    },
    {
        "name": "predict_og",
        "description": "Predict original gravity from a grain bill. ESTIMATED.",
        "parameters": {
            "type": "object",
            "properties": {
                "fermentables": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "[pounds, points per pound per gallon]",
                    },
                },
                "batch_gal": {"type": "number"},
                "efficiency": {"type": "number"},
            },
            "required": ["fermentables", "batch_gal"],
        },
    },
    {
        "name": "batch_summary",
        "description": "Everything recorded about a batch, with provenance on each value.",
        "parameters": {
            "type": "object",
            "properties": {"batch_id": {"type": "integer"}},
            "required": ["batch_id"],
        },
    },
    {
        "name": "list_batches",
        "description": "All batches, newest first.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_inventory",
        "description": "Current inventory with provenance.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_reference",
        "description": "Search stored reference notes. Results carry their source URL.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "spend_by_vendor",
        "description": "Purchase totals grouped by vendor.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _value_to_tool_result(value) -> dict[str, Any]:
    return {"ok": True, "result": value.to_dict()}


def build_registry(store: Store) -> dict[str, Callable[..., Any]]:
    def estimate_abv(og: float, fg: float, method: str = "alternate"):
        return _value_to_tool_result(brewing.abv_estimate(og, fg, method))

    def correct_hydrometer(sg: float, temp_f: float, cal_temp_f: float = 60.0):
        return _value_to_tool_result(
            brewing.hydrometer_reading(sg, temp_f, cal_temp_f)
        )

    def convert_gravity(sg: float | None = None, plato: float | None = None):
        if sg is not None:
            return {"ok": True, "result": {"sg": sg, "plato": round(brewing.sg_to_plato(sg), 3)}}
        if plato is not None:
            return {"ok": True, "result": {"plato": plato, "sg": round(brewing.plato_to_sg(plato), 4)}}
        return {"ok": False, "error": "give either sg or plato"}

    def predict_og(fermentables, batch_gal, efficiency: float = 0.72):
        parts = [(float(lb), float(ppg)) for lb, ppg in fermentables]
        return _value_to_tool_result(brewing.og_from_fermentables(parts, batch_gal, efficiency))

    def batch_summary(batch_id: int):
        return {"ok": True, "result": store.batch_summary(int(batch_id))}

    def list_batches():
        return {"ok": True, "result": store.list_batches()}

    def list_inventory():
        return {"ok": True, "result": store.list_inventory()}

    def search_reference(query: str):
        return {"ok": True, "result": store.search_reference(query)}

    def spend_by_vendor():
        return {"ok": True, "result": store.spend_by_vendor()}

    return {
        "estimate_abv": estimate_abv,
        "correct_hydrometer": correct_hydrometer,
        "convert_gravity": convert_gravity,
        "predict_og": predict_og,
        "batch_summary": batch_summary,
        "list_batches": list_batches,
        "list_inventory": list_inventory,
        "search_reference": search_reference,
        "spend_by_vendor": spend_by_vendor,
    }


def run_tool(store: Store, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = build_registry(store)
    if name not in registry:
        return {"ok": False, "error": f"unknown tool {name!r}", "available": sorted(registry)}
    try:
        return registry[name](**(args or {}))
    except (ValueError, TypeError, KeyError) as exc:
        return {"ok": False, "error": str(exc)}
