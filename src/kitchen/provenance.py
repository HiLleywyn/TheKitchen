"""Provenance-typed values.

Every number TheKitchen stores or reports carries how it came to exist. The one
invariant that matters: a weaker claim is never presented as a stronger one.
Estimated ABV is not a measurement. An inferred batch state is not an
observation. A recipe's expected gravity is not a reading.

`Value` is frozen, so a kind cannot be reassigned after construction, and
`recast` only permits weakening a claim, never strengthening it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    MEASURED = "measured"
    CALCULATED = "calculated"
    USER_SUPPLIED = "user_supplied"
    ESTIMATED = "estimated"
    INFERRED = "inferred"


# How strong the claim is. Higher means harder to dispute.
CLAIM_RANK = {
    Kind.MEASURED: 5,
    Kind.CALCULATED: 4,
    Kind.USER_SUPPLIED: 3,
    Kind.ESTIMATED: 2,
    Kind.INFERRED: 1,
}


class ProvenanceError(ValueError):
    """A value would have been presented as stronger evidence than it is."""


def coerce_kind(kind: Kind | str) -> Kind:
    """Accept a Kind or its string value. Never a repr like 'Kind.MEASURED'."""
    if isinstance(kind, Kind):
        return kind
    try:
        return Kind(str(kind))
    except ValueError as exc:
        raise ProvenanceError(
            f"unknown provenance kind {kind!r}; expected one of "
            f"{[k.value for k in Kind]}"
        ) from exc


@dataclass(frozen=True)
class Value:
    amount: float
    unit: str
    kind: Kind
    method: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, Kind):
            object.__setattr__(self, "kind", coerce_kind(self.kind))
        if self.kind in (Kind.MEASURED, Kind.CALCULATED) and not self.method:
            raise ProvenanceError(
                f"{self.kind.value} value needs a method: how was it obtained?"
            )

    def recast(self, kind: Kind | str, method: str = "", source: str = "") -> "Value":
        """Return this value under a weaker (or equal) claim."""
        kind = coerce_kind(kind)
        if CLAIM_RANK[kind] > CLAIM_RANK[self.kind]:
            raise ProvenanceError(
                f"cannot present a {self.kind.value} value as {kind.value}"
            )
        return Value(self.amount, self.unit, kind, method or self.method, source or self.source)

    def require(self, minimum: Kind | str) -> "Value":
        """Return self, or raise if the claim is weaker than `minimum`."""
        minimum = coerce_kind(minimum)
        if CLAIM_RANK[self.kind] < CLAIM_RANK[minimum]:
            raise ProvenanceError(
                f"{self.kind.value} value is weaker than the required {minimum.value}"
            )
        return self

    @property
    def is_measurement(self) -> bool:
        return self.kind is Kind.MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.amount, 6),
            "unit": self.unit,
            "kind": self.kind.value,
            "method": self.method,
            "source": self.source,
        }

    def __str__(self) -> str:
        return f"{self.amount:g} {self.unit} ({self.kind.value})"


def as_value(payload: dict[str, Any]) -> Value:
    return Value(
        amount=float(payload["value"]),
        unit=str(payload["unit"]),
        kind=coerce_kind(payload["kind"]),
        method=str(payload.get("method") or ""),
        source=str(payload.get("source") or ""),
    )
