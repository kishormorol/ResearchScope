"""Abstract base connector for data sources."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.normalization.schema import Paper


class BaseConnector(ABC):
    """Base class for all data source connectors."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for the data source."""

    @abstractmethod
    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        """Fetch papers matching *query* from the data source."""
