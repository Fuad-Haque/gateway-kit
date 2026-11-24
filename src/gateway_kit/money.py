"""Exact decimal helpers. Money is never a float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .errors import ValidationError

PER_MILLION = Decimal(1_000_000)


def to_decimal(value: Any, field: str = "value") -> Decimal:
    """Convert int/str/Decimal/float to Decimal; reject bool and junk."""
    if isinstance(value, bool):
        raise ValidationError(f"{field}: booleans are not numbers")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValidationError(f"{field}: {value!r} is not a number") from None
    elif isinstance(value, float):
        result = Decimal(str(value))  # str() avoids binary-float noise
    else:
        raise ValidationError(f"{field}: {value!r} is not a number")
    if not result.is_finite():
        raise ValidationError(f"{field}: must be finite")
    return result


def quantize(x: Decimal, places: int = 2) -> Decimal:
    """Round half-up to `places` decimals (finance-style rounding)."""
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fmt_usd(x: Decimal, places: int = 2) -> str:
    q = quantize(x, places)
    sign = "-" if q < 0 else ""
    return f"{sign}${abs(q):,.{places}f}"
