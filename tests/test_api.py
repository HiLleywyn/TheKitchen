import pytest
from fastapi.testclient import TestClient

from kitchen import api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KITCHEN_DB", str(tmp_path / "api.db"))
    monkeypatch.setattr(api, "_STORE", None)
    with TestClient(api.app) as test_client:
        yield test_client


def make_batch(client, code="B-100"):
    res = client.post("/api/batches", json={"code": code, "name": "Test porter"})
    assert res.status_code == 201, res.text
    return res.json()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_index_page_serves(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "TheKitchen" in res.text


def test_batch_lifecycle(client):
    batch = make_batch(client)
    assert batch["status_source"] == "inferred"

    res = client.post(
        f"/api/batches/{batch['id']}/gravity",
        json={"sg": 1.046, "temp_f": 80.0, "note": "post-boil"},
    )
    assert res.status_code == 201, res.text
    reading = res.json()
    assert reading["provenance_kind"] == "measured"
    assert reading["amount"] == pytest.approx(1.0484, abs=0.0005)
    assert "corrected to 60 F" in reading["method"]

    client.post(f"/api/batches/{batch['id']}/gravity", json={"sg": 1.011, "temp_f": 68.0})

    summary = client.get(f"/api/batches/{batch['id']}").json()
    assert summary["abv"]["kind"] == "estimated"
    assert summary["first_gravity"]["kind"] == "measured"
    assert summary["status"]["kind"] == "inferred"


def test_duplicate_batch_code_is_rejected(client):
    make_batch(client, "B-200")
    res = client.post("/api/batches", json={"code": "B-200"})
    assert res.status_code == 400


def test_missing_batch_is_404(client):
    assert client.get("/api/batches/999").status_code == 404


def test_reading_on_missing_batch_is_404(client):
    res = client.post("/api/batches/999/gravity", json={"sg": 1.040, "temp_f": 68.0})
    assert res.status_code == 404


def test_measured_reading_without_method_is_400(client):
    batch = make_batch(client, "B-300")
    res = client.post(
        f"/api/batches/{batch['id']}/readings",
        json={"kind": "gravity", "amount": 1.05, "unit": "SG", "provenance_kind": "measured"},
    )
    assert res.status_code == 400


def test_recipe_round_trip(client):
    res = client.post(
        "/api/recipes",
        json={
            "name": "Dry mead",
            "batch_size_gal": 5,
            "ingredients": [{"name": "Wildflower honey", "amount": 12, "unit": "lb"}],
        },
    )
    assert res.status_code == 201
    recipe_id = res.json()["id"]
    assert client.get(f"/api/recipes/{recipe_id}").json()["ingredients"][0]["name"] == "Wildflower honey"


def test_inventory_and_spend(client):
    client.post("/api/inventory", json={"name": "Cascade hops", "amount": 4, "unit": "oz", "category": "hop"})
    assert client.get("/api/inventory").json()[0]["name"] == "Cascade hops"

    client.post(
        "/api/purchases",
        json={
            "vendor": "Shop",
            "lines": [{"description": "Hops", "qty": 2, "unit": "oz", "unit_price": 3.0}],
        },
    )
    assert client.get("/api/spend").json()[0]["total"] == pytest.approx(6.0)


def test_reference_needs_a_source(client):
    res = client.post("/api/reference", json={"title": "x", "body": "y"})
    assert res.status_code == 422  # source_url is required by the schema


def test_tool_registry_exposes_abv_as_estimated(client):
    specs = client.get("/api/tools").json()
    assert any(spec["name"] == "estimate_abv" for spec in specs)

    res = client.post("/api/tools/run", json={"tool": "estimate_abv", "args": {"og": 1.052, "fg": 1.011}})
    body = res.json()
    assert body["result"]["kind"] == "estimated"


def test_unknown_tool_is_400(client):
    res = client.post("/api/tools/run", json={"tool": "brew_beer", "args": {}})
    assert res.status_code == 400
