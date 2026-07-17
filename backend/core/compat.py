"""Small runtime compatibility aliases for the temporary Python 3.10 launcher."""

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - exercised only by Python 3.10
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - exercised only by Python 3.10
    from enum import Enum

    class StrEnum(str, Enum):  # noqa: UP042
        def __str__(self) -> str:
            return self.value


__all__ = ["UTC", "StrEnum"]
