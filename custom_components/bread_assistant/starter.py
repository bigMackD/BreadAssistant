"""Optional future Starter Manager boundary; never a baking dependency."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class StarterReadiness(StrEnum):
    UNKNOWN = "unknown"
    NOT_READY = "not_ready"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class StarterInfo:
    id: str
    name: str
    last_fed_at: datetime | None = None
    readiness: StarterReadiness = StarterReadiness.UNKNOWN
    metadata: Mapping[str, str | int | float | bool | None] = field(
        default_factory=dict
    )


class StarterProvider(Protocol):
    """An optional domain interface. Provider facts never confirm a bake gate."""

    async def async_get_starter(self, starter_id: str) -> StarterInfo | None:
        """Retrieve a snapshot, or None for an unavailable/unknown starter."""
        ...
