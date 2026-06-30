"""Value objects - immutable objects defined by their attributes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

from forex_trading.core.domain.entities import ValueObject


class UniqueId(ValueObject):
    """Unique identifier value object."""

    def __init__(self, value: UUID | None = None) -> None:
        self._value = value or uuid4()

    @property
    def value(self) -> UUID:
        return self._value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UniqueId):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"UniqueId({self._value})"


class Money(ValueObject):
    """Money value object with currency."""

    def __init__(self, amount: Decimal | float | str, currency: str = "USD") -> None:
        self._amount = Decimal(str(amount))
        self._currency = currency.upper()

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency(self) -> str:
        return self._currency

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self._amount == other._amount and self._currency == other._currency

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __add__(self, other: Self) -> Self:
        if self._currency != other._currency:
            raise ValueError(f"Cannot add different currencies: {self._currency} and {other._currency}")
        return Money(self._amount + other._amount, self._currency)

    def __sub__(self, other: Self) -> Self:
        if self._currency != other._currency:
            raise ValueError(f"Cannot subtract different currencies: {self._currency} and {other._currency}")
        return Money(self._amount - other._amount, self._currency)

    def __mul__(self, factor: float | Decimal) -> Self:
        return Money(self._amount * Decimal(str(factor)), self._currency)

    def __gt__(self, other: Self) -> bool:
        if self._currency != other._currency:
            raise ValueError("Cannot compare different currencies")
        return self._amount > other._amount

    def __ge__(self, other: Self) -> bool:
        if self._currency != other._currency:
            raise ValueError("Cannot compare different currencies")
        return self._amount >= other._amount

    def __lt__(self, other: Self) -> bool:
        if self._currency != other._currency:
            raise ValueError("Cannot compare different currencies")
        return self._amount < other._amount

    def __le__(self, other: Self) -> bool:
        if self._currency != other._currency:
            raise ValueError("Cannot compare different currencies")
        return self._amount <= other._amount

    def __str__(self) -> str:
        return f"{self._amount:.2f} {self._currency}"

    def __repr__(self) -> str:
        return f"Money({self._amount}, '{self._currency}')"


class Symbol(ValueObject):
    """Trading symbol value object (e.g., EUR/USD)."""

    # Standard Forex pairs
    MAJOR_PAIRS = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"
    ]

    def __init__(self, value: str) -> None:
        normalized = value.upper().replace("/", "").replace(" ", "")
        if not normalized or len(normalized) < 6:
            raise ValueError(f"Invalid symbol: {value}")
        self._value = normalized

    @property
    def value(self) -> str:
        return self._value

    @property
    def base(self) -> str:
        """Get base currency (first 3 characters)."""
        return self._value[:3]

    @property
    def quote(self) -> str:
        """Get quote currency (last 3 characters)."""
        return self._value[3:]

    @property
    def is_major(self) -> bool:
        """Check if this is a major pair."""
        return self._value in self.MAJOR_PAIRS

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return f"{self._value[:3]}/{self._value[3:]}"

    def __repr__(self) -> str:
        return f"Symbol('{self._value}')"


class Timestamp(ValueObject):
    """Timestamp value object with timezone awareness."""

    def __init__(self, value: datetime | None = None) -> None:
        self._value = value or datetime.utcnow()

    @property
    def value(self) -> datetime:
        return self._value

    @property
    def epoch(self) -> float:
        return self._value.timestamp()

    @property
    def date(self) -> str:
        return self._value.strftime("%Y-%m-%d")

    @property
    def time(self) -> str:
        return self._value.strftime("%H:%M:%S")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Timestamp):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __gt__(self, other: Self) -> bool:
        return self._value > other._value

    def __ge__(self, other: Self) -> bool:
        return self._value >= other._value

    def __lt__(self, other: Self) -> bool:
        return self._value < other._value

    def __le__(self, other: Self) -> bool:
        return self._value <= other._value

    def __str__(self) -> str:
        return self._value.isoformat()

    def __repr__(self) -> str:
        return f"Timestamp('{self._value.isoformat()}')"
