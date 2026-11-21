"""Brewing calculations, each returning a Value tagged with its provenance.

Measured: a hydrometer or thermometer reading, with the instrument's correction
recorded in `method`.
Calculated: arithmetic on measured inputs (attenuation, blended gravity).
Estimated: a model output (ABV from two gravities, gravity from a grain bill).

None of these functions will hand back a measurement it did not receive.
"""

from __future__ import annotations

from .provenance import Kind, Value

ABV_METHODS = ("simple", "alternate")


def sg_to_plato(sg: float) -> float:
    """Plato from specific gravity (polynomial, good from about 1.000 to 1.130)."""
    return -616.868 + 1111.14 * sg - 630.272 * sg**2 + 135.997 * sg**3


def plato_to_sg(plato: float) -> float:
    """Inverse of sg_to_plato by bisection."""
    lo, hi = 0.950, 1.250
    for _ in range(80):
        mid = (lo + hi) / 2
        if sg_to_plato(mid) < plato:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def gravity_points(sg: float) -> float:
    """Points of gravity: 1.048 -> 48.0."""
    return (sg - 1.0) * 1000.0


def _hydrometer_factor(temp_f: float) -> float:
    return (
        1.00130346
        - 1.34722124e-4 * temp_f
        + 2.04052596e-6 * temp_f**2
        - 2.32820948e-9 * temp_f**3
    )


def correct_hydrometer(sg: float, temp_f: float, cal_temp_f: float = 60.0) -> float:
    """Temperature-correct a hydrometer reading to its calibration temperature."""
    return sg * _hydrometer_factor(temp_f) / _hydrometer_factor(cal_temp_f)


def hydrometer_reading(
    sg: float, temp_f: float, cal_temp_f: float = 60.0, note: str = ""
) -> Value:
    """A hydrometer reading, corrected. Still a measurement, not a model output."""
    corrected = correct_hydrometer(sg, temp_f, cal_temp_f)
    method = (
        f"hydrometer read {sg:.4f} at {temp_f:g} F, corrected to {cal_temp_f:g} F"
        + (f"; {note}" if note else "")
    )
    return Value(corrected, "SG", Kind.MEASURED, method=method)


def abv_estimate(og: float, fg: float, method: str = "alternate") -> Value:
    """Estimated alcohol by volume from two measured gravities.

    This is a model output. It is never a measurement, no matter how good the
    two gravities were.
    """
    if method not in ABV_METHODS:
        raise ValueError(f"unknown ABV method {method!r}; expected one of {ABV_METHODS}")
    if og <= 1.0:
        raise ValueError("original gravity must be above 1.000")
    if fg > og:
        raise ValueError(
            f"final gravity {fg:.4f} is above original gravity {og:.4f}; "
            "check the readings or the reading order"
        )
    if method == "simple":
        abv = (og - fg) * 131.25
        label = "ABV = (OG - FG) x 131.25"
    else:
        abv = 76.08 * (og - fg) / (1.775 - og) * (fg / 0.794)
        label = "ABV = 76.08(OG-FG)/(1.775-OG) x FG/0.794"
    return Value(
        abv,
        "% ABV",
        Kind.ESTIMATED,
        method=f"{label}; estimated from OG {og:.4f} and FG {fg:.4f}, not measured",
    )


def apparent_attenuation(og: float, fg: float) -> Value:
    """Apparent attenuation from two measured gravities."""
    if og <= 1.0:
        raise ValueError("original gravity must be above 1.000")
    if fg > og:
        raise ValueError("final gravity is above original gravity")
    pct = (og - fg) / (og - 1.0) * 100.0
    return Value(
        pct,
        "%",
        Kind.CALCULATED,
        method=f"apparent attenuation = (OG-FG)/(OG-1) from {og:.4f} and {fg:.4f}",
    )


def blend_gravity(parts: list[tuple[float, float]]) -> Value:
    """Gravity after combining volumes: [(gallons, SG), ...]."""
    total_vol = sum(v for v, _ in parts)
    if total_vol <= 0:
        raise ValueError("total volume must be positive")
    points = sum(v * gravity_points(sg) for v, sg in parts) / total_vol
    return Value(
        1.0 + points / 1000.0,
        "SG",
        Kind.CALCULATED,
        method=f"volume-weighted blend of {len(parts)} portions, {total_vol:g} gal total",
    )


def og_from_fermentables(
    fermentables: list[tuple[float, float]],
    batch_gal: float,
    efficiency: float = 0.72,
) -> Value:
    """Predicted original gravity from a grain bill: [(pounds, ppg), ...]."""
    if batch_gal <= 0:
        raise ValueError("batch volume must be positive")
    if not 0 < efficiency <= 1:
        raise ValueError("efficiency must be between 0 and 1")
    points = sum(lb * ppg for lb, ppg in fermentables) * efficiency
    return Value(
        1.0 + points / batch_gal / 1000.0,
        "SG",
        Kind.ESTIMATED,
        method=(
            f"extract model: sum(lb x ppg) x {efficiency:.0%} efficiency "
            f"/ {batch_gal:g} gal; predicted, not measured"
        ),
    )
