import pytest

from kitchen import brewing
from kitchen.provenance import Kind


def test_plato_round_trip():
    for sg in (1.006, 1.012, 1.048, 1.090, 1.120):
        assert brewing.plato_to_sg(brewing.sg_to_plato(sg)) == pytest.approx(sg, abs=1e-4)


def test_plato_reference_points():
    assert brewing.sg_to_plato(1.048) == pytest.approx(11.9, abs=0.1)
    assert brewing.sg_to_plato(1.010) == pytest.approx(2.56, abs=0.1)


def test_gravity_points():
    assert brewing.gravity_points(1.048) == pytest.approx(48.0)


def test_hydrometer_correction_raises_a_warm_reading():
    # a warm sample reads low, so the correction must move the value up
    corrected = brewing.correct_hydrometer(1.046, 80.0)
    assert corrected > 1.046
    assert corrected == pytest.approx(1.0484, abs=0.0005)


def test_hydrometer_correction_is_identity_at_calibration_temp():
    assert brewing.correct_hydrometer(1.050, 60.0) == pytest.approx(1.050, abs=1e-9)


def test_hydrometer_reading_is_measured_with_method():
    value = brewing.hydrometer_reading(1.046, 80.0)
    assert value.kind is Kind.MEASURED
    assert "80 F" in value.method and "60 F" in value.method


def test_abv_is_estimated_never_measured():
    value = brewing.abv_estimate(1.052, 1.011)
    assert value.kind is Kind.ESTIMATED
    assert "not measured" in value.method


def test_abv_alternate_matches_known_range():
    # 1.052 -> 1.011 is a typical 5.3-5.4% ale
    assert brewing.abv_estimate(1.052, 1.011, "alternate").amount == pytest.approx(5.4, abs=0.15)
    assert brewing.abv_estimate(1.052, 1.011, "simple").amount == pytest.approx(5.38, abs=0.05)


def test_abv_rejects_final_above_original():
    with pytest.raises(ValueError):
        brewing.abv_estimate(1.010, 1.052)


def test_abv_rejects_unknown_method():
    with pytest.raises(ValueError):
        brewing.abv_estimate(1.052, 1.011, "vibes")


def test_attenuation_is_calculated():
    value = brewing.apparent_attenuation(1.052, 1.011)
    assert value.kind is Kind.CALCULATED
    assert value.amount == pytest.approx(78.8, abs=0.2)


def test_blend_gravity_is_volume_weighted():
    value = brewing.blend_gravity([(4.0, 1.060), (1.0, 1.000)])
    assert value.kind is Kind.CALCULATED
    assert value.amount == pytest.approx(1.048, abs=0.0005)


def test_predict_og_is_estimated():
    value = brewing.og_from_fermentables([(10.0, 36.0), (1.0, 34.0)], batch_gal=5.0)
    assert value.kind is Kind.ESTIMATED
    # 394 points * 0.72 / 5 gal = 56.7 -> 1.057
    assert value.amount == pytest.approx(1.057, abs=0.001)


def test_predict_og_rejects_bad_efficiency():
    with pytest.raises(ValueError):
        brewing.og_from_fermentables([(10.0, 36.0)], 5.0, efficiency=1.5)
