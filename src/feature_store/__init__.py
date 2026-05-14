"""Real-time feature store backed by Redis with in-memory fallback."""
from .redis_store import RedisFeatureStore

__all__ = ["RedisFeatureStore"]
