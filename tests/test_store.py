import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from kitchen.provenance import Kind
from kitchen.store import Store


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "test.db")


def iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(microsecond=0).isoformat()


def test_recipe_with_ingredients(store):
    recipe = store.create_recipe(
        "House porter",
        style="Robust Porter",
        batch_size_gal=5.0,
        ingredients=[
            {"name": "Maris Otter", "amount": 9.5, "unit": "lb", "category": "fermentable"},
            {"name": "Chocolate malt", "amount": 0.75, "unit": "lb", "category": "fermentable"},
        ],
    )
    assert recipe["id"] == 1
    assert len(recipe["ingredients"]) == 2
    assert recipe["ingredients"][0]["provenance_kind"] == "user_supplied"


def test_batch_status_defaults_to_inferred(store):
    batch = store.create_batch("B-001", started_at=iso(0))
    assert batch["status_source"] == Kind.INFERRED.value
    assert batch["status"] is None


def test_user_set_status_is_marked_user_supplied(store):
    batch = store.create_batch("B-002", status="kegged")
    assert batch["status_source"] == Kind.USER_SUPPLIED.value


def test_measured_reading_requires_method(store):
    batch = store.create_batch("B-003")
    with pytest.raises(ValueError):
        store.add_reading(batch["id"], "gravity", 1.050, "SG", Kind.MEASURED.value)


def test_unknown_reading_kind_is_rejected(store):
    batch = store.create_batch("B-004")
    with pytest.raises(ValueError):
        store.add_reading(batch["id"], "vibes", 1.0, "each", Kind.USER_SUPPLIED.value)


def test_readings_are_append_only(store):
    batch = store.create_batch("B-005")
    reading = store.add_reading(
        batch["id"], "gravity", 1.050, "SG", Kind.MEASURED.value, method="hydrometer"
    )
    with pytest.raises(sqlite3.Error) as exc:
        with store.connect() as conn:
            conn.execute("UPDATE readings SET amount = 1.020 WHERE id = ?", (reading["id"],))
    assert "append-only" in str(exc.value)

    with pytest.raises(sqlite3.Error):
        with store.connect() as conn:
            conn.execute("DELETE FROM readings WHERE id = ?", (reading["id"],))


def test_summary_reports_abv_as_estimated(store):
    batch = store.create_batch("B-006", started_at=iso(14))
    store.add_reading(
        batch["id"], "gravity", 1.052, "SG", Kind.MEASURED.value,
        method="hydrometer at 68 F, corrected to 60 F", taken_at=iso(14),
    )
    store.add_reading(
        batch["id"], "gravity", 1.011, "SG", Kind.MEASURED.value,
        method="hydrometer at 68 F, corrected to 60 F", taken_at=iso(1),
    )
    summary = store.batch_summary(batch["id"])
    assert summary["abv"]["kind"] == Kind.ESTIMATED.value
    assert summary["abv"]["value"] == pytest.approx(5.49, abs=0.05)
    assert summary["first_gravity"]["kind"] == Kind.MEASURED.value
    assert summary["latest_gravity"]["kind"] == Kind.MEASURED.value
    assert summary["apparent_attenuation"]["kind"] == Kind.CALCULATED.value


def test_summary_without_readings_does_not_invent_abv(store):
    batch = store.create_batch("B-007")
    summary = store.batch_summary(batch["id"])
    assert summary["abv"] is None
    assert summary["status"]["kind"] == Kind.INFERRED.value
    assert summary["status"]["value"] == "unknown"
    assert any("no gravity readings" in c for c in summary["caveats"])


def test_summary_flags_a_late_first_reading(store):
    batch = store.create_batch("B-008", started_at=iso(10))
    store.add_reading(
        batch["id"], "gravity", 1.030, "SG", Kind.MEASURED.value,
        method="hydrometer", taken_at=iso(3),
    )
    summary = store.batch_summary(batch["id"])
    assert any("after the batch started" in c for c in summary["caveats"])


def test_stable_gravity_is_inferred_not_observed(store):
    batch = store.create_batch("B-009", started_at=iso(20))
    for days in (12, 8):
        store.add_reading(
            batch["id"], "gravity", 1.010, "SG", Kind.MEASURED.value,
            method="hydrometer", taken_at=iso(days),
        )
    summary = store.batch_summary(batch["id"])
    assert summary["status"]["kind"] == Kind.INFERRED.value
    assert "likely ready" in summary["status"]["value"]


def test_transfers_are_recorded_in_order(store):
    batch = store.create_batch("B-010")
    store.add_transfer(batch["id"], "carboy", from_vessel="bucket", occurred_at=iso(3))
    store.add_transfer(batch["id"], "keg", from_vessel="carboy", occurred_at=iso(1))
    transfers = store.list_transfers(batch["id"])
    assert [t["to_vessel"] for t in transfers] == ["carboy", "keg"]


def test_inventory_upsert_keeps_one_row(store):
    store.upsert_inventory("Cascade hops", 8, "oz", "hop")
    store.upsert_inventory("Cascade hops", 3, "oz", "hop")
    items = store.list_inventory()
    assert len(items) == 1
    assert items[0]["amount"] == 3


def test_purchase_totals_are_summed(store):
    purchase = store.add_purchase(
        "Local homebrew shop",
        lines=[
            {"description": "Maris Otter", "qty": 10, "unit": "lb", "unit_price": 1.4},
            {"description": "US-05", "qty": 2, "unit": "pack", "unit_price": 4.5},
        ],
        invoice_no="A-1042",
    )
    assert purchase["total"] == pytest.approx(23.0)
    assert len(purchase["lines"]) == 2
    assert store.spend_by_vendor()[0]["total"] == pytest.approx(23.0)


def test_reference_requires_a_source(store):
    with pytest.raises(ValueError):
        store.add_reference("Mash pH", "Aim for 5.2 to 5.4.")


def test_reference_search_returns_source(store):
    store.add_reference(
        "Mash pH",
        "Aim for 5.2 to 5.4 at room temperature.",
        source_url="https://example.com/mash-ph",
        source_title="Brewing water guide",
    )
    hits = store.search_reference("pH")
    assert hits[0]["source_url"] == "https://example.com/mash-ph"
