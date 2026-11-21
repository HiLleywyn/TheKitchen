import pytest

from kitchen.provenance import Kind, ProvenanceError, Value


def test_measured_value_needs_a_method():
    with pytest.raises(ProvenanceError):
        Value(1.048, "SG", Kind.MEASURED)


def test_estimated_value_can_omit_method():
    assert Value(5.2, "% ABV", Kind.ESTIMATED).kind is Kind.ESTIMATED


def test_recast_can_weaken_a_claim():
    measured = Value(1.048, "SG", Kind.MEASURED, method="hydrometer")
    weaker = measured.recast(Kind.ESTIMATED, method="rounded")
    assert weaker.kind is Kind.ESTIMATED
    assert weaker.amount == measured.amount


@pytest.mark.parametrize("target", [Kind.MEASURED, Kind.CALCULATED, Kind.USER_SUPPLIED])
def test_recast_cannot_strengthen_a_claim(target):
    estimated = Value(5.2, "% ABV", Kind.ESTIMATED, method="from two gravities")
    with pytest.raises(ProvenanceError):
        estimated.recast(target)


def test_value_is_frozen():
    value = Value(5.2, "% ABV", Kind.ESTIMATED)
    with pytest.raises(Exception):
        value.kind = Kind.MEASURED  # type: ignore[misc]


def test_require_rejects_a_weaker_claim():
    estimated = Value(5.2, "% ABV", Kind.ESTIMATED)
    with pytest.raises(ProvenanceError):
        estimated.require(Kind.MEASURED)


def test_to_dict_always_carries_provenance():
    payload = Value(1.012, "SG", Kind.MEASURED, method="hydrometer").to_dict()
    assert payload["kind"] == "measured"
    assert payload["method"] == "hydrometer"
    assert payload["value"] == 1.012
