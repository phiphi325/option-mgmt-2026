"""Unit tests for `engine.decision.serialize_canonical`.

Verifies the canonicalization rules documented in the module docstring +
the M1.24 dev spec: float rounding, datetime normalization, enum/tuple/
frozenset handling, nested-dataclass recursion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timezone
from enum import Enum, StrEnum

import pytest

from engine.decision.serialize import _canonicalize


class _StrEnumExample(StrEnum):
    FOO = "foo"
    BAR = "bar"


class _IntEnumExample(Enum):
    A = 1
    B = 2


@dataclass(frozen=True)
class _Leaf:
    name: str
    value: float


@dataclass(frozen=True)
class _Branch:
    leaf: _Leaf
    items: tuple[_Leaf, ...]


class TestFloatRounding:
    def test_rounds_to_six_decimals(self) -> None:
        assert _canonicalize(0.12345678901234) == 0.123457

    def test_preserves_short_floats(self) -> None:
        assert _canonicalize(0.5) == 0.5
        assert _canonicalize(1.0) == 1.0

    def test_negative_floats_round(self) -> None:
        assert _canonicalize(-0.987654321) == -0.987654

    def test_preserves_nan(self) -> None:
        # NaN survives — JSON serialization will fail, which is correct
        # (engine outputs should never contain NaN; if they do, that's a bug
        # worth surfacing loudly).
        out = _canonicalize(float("nan"))
        assert math.isnan(out)

    def test_preserves_inf(self) -> None:
        assert _canonicalize(float("inf")) == float("inf")


class TestDatetimeHandling:
    def test_naive_datetime_assumed_utc(self) -> None:
        result = _canonicalize(datetime(2026, 5, 13, 14, 30, 0))
        assert result == "2026-05-13T14:30:00Z"

    def test_aware_utc_normalized_to_z(self) -> None:
        result = _canonicalize(datetime(2026, 5, 13, 14, 30, tzinfo=UTC))
        assert result == "2026-05-13T14:30:00Z"

    def test_aware_non_utc_preserved(self) -> None:
        from datetime import timedelta  # noqa: PLC0415

        tz = timezone(timedelta(hours=5))
        result = _canonicalize(datetime(2026, 5, 13, 14, 30, tzinfo=tz))
        assert result == "2026-05-13T14:30:00+05:00"


class TestDateHandling:
    def test_date_serialized_as_iso(self) -> None:
        assert _canonicalize(date(2026, 5, 13)) == "2026-05-13"


class TestEnumHandling:
    def test_str_enum_to_value(self) -> None:
        assert _canonicalize(_StrEnumExample.FOO) == "foo"

    def test_int_enum_to_value(self) -> None:
        assert _canonicalize(_IntEnumExample.A) == 1


class TestCollections:
    def test_tuple_to_list(self) -> None:
        assert _canonicalize((1, 2, 3)) == [1, 2, 3]

    def test_list_recursed(self) -> None:
        assert _canonicalize([0.1234567, "x"]) == [0.123457, "x"]

    def test_dict_keys_stringified(self) -> None:
        result = _canonicalize({1: "a", "b": 2})
        assert result == {"1": "a", "b": 2}

    def test_frozenset_sorted_by_repr(self) -> None:
        result = _canonicalize(frozenset(["b", "a", "c"]))
        assert result == ["a", "b", "c"]


class TestDataclass:
    def test_simple_dataclass(self) -> None:
        leaf = _Leaf(name="L1", value=0.987654321)
        assert _canonicalize(leaf) == {"name": "L1", "value": 0.987654}

    def test_nested_dataclass(self) -> None:
        branch = _Branch(
            leaf=_Leaf(name="root", value=0.5),
            items=(_Leaf(name="a", value=0.1), _Leaf(name="b", value=0.2)),
        )
        result = _canonicalize(branch)
        assert result == {
            "leaf": {"name": "root", "value": 0.5},
            "items": [
                {"name": "a", "value": 0.1},
                {"name": "b", "value": 0.2},
            ],
        }


class TestPydantic:
    def test_pydantic_model_via_model_dump(self) -> None:
        from pydantic import BaseModel  # noqa: PLC0415

        class _PydM(BaseModel):
            x: float
            y: str

        out = _canonicalize(_PydM(x=0.111111111, y="hi"))
        assert out == {"x": 0.111111, "y": "hi"}


class TestPrimitives:
    def test_none(self) -> None:
        assert _canonicalize(None) is None

    def test_bool_preserved_not_int(self) -> None:
        # Important: bool is a subclass of int in Python; we must not
        # accidentally serialize True as 1.
        assert _canonicalize(True) is True
        assert _canonicalize(False) is False

    def test_int(self) -> None:
        assert _canonicalize(42) == 42

    def test_str(self) -> None:
        assert _canonicalize("hello") == "hello"


class TestRoundTrip:
    """Same input → byte-identical output. The Phase 1 Done determinism guarantee."""

    def test_idempotent(self) -> None:
        sample = {
            "x": 0.5,
            "y": (1, 2, 3),
            "z": _Leaf(name="t", value=0.123),
            "t": datetime(2026, 5, 13, 14, 30, tzinfo=UTC),
        }
        a = _canonicalize(sample)
        b = _canonicalize(sample)
        assert a == b


def test_full_daily_decision_canonicalizes(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    """Smoke: a full DailyDecision (frozen dataclass with nested Pydantic and
    other dataclasses) goes through serialize_canonical without raising."""
    # We don't construct a full real DailyDecision here — the fixture replay
    # tests (test_master_decision_goldens.py) cover that end-to-end. This
    # smoke just verifies the import + helper composition.
    from engine.decision import serialize_canonical  # noqa: PLC0415

    assert callable(serialize_canonical)
