"""Runtime-managed model components."""

from backend.components.manager import ComponentManager
from backend.components.protocol import EmbeddingProviderClient, ProviderMetadata

__all__ = ["ComponentManager", "EmbeddingProviderClient", "ProviderMetadata"]

