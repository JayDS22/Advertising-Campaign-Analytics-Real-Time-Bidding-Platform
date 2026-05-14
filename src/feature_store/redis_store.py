"""Online feature store. Redis-backed, with an in-memory fallback so the
rest of the platform stays usable when Redis is not reachable (CI, demo).

Stored shapes: user embeddings (float32 byte buffers), behavioral feature
dicts, and audience-segment set membership.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import numpy as np

try:
    import redis  # type: ignore
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class RedisFeatureStore:
    """Redis client wrapper with a process-local dict fallback.

    The constructor pings Redis once with a tight timeout. On any failure
    (no host, network blip, auth) it silently switches to the in-memory
    path so the bidder never blocks on the feature store.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0,
                 ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._memory: dict[str, Any] = {}
        self._client = None
        if HAS_REDIS:
            try:
                self._client = redis.Redis(host=host, port=port, db=db,
                                            socket_connect_timeout=0.2,
                                            decode_responses=False)
                self._client.ping()
            except Exception:
                self._client = None

    def _key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    # ---- Embeddings ----

    def get_user_embedding(self, user_id: str) -> Optional[np.ndarray]:
        k = self._key("emb:user", user_id)
        if self._client is not None:
            try:
                raw = self._client.get(k)
                if raw is None:
                    return None
                return np.frombuffer(raw, dtype=np.float32)
            except Exception:
                pass
        v = self._memory.get(k)
        return v.copy() if v is not None else None

    def set_user_embedding(self, user_id: str, emb: np.ndarray) -> None:
        emb32 = np.asarray(emb, dtype=np.float32)
        k = self._key("emb:user", user_id)
        if self._client is not None:
            try:
                self._client.setex(k, self.ttl, emb32.tobytes())
                return
            except Exception:
                pass
        self._memory[k] = emb32

    # ---- Generic features ----

    def get_features(self, entity: str, entity_id: str) -> dict:
        k = self._key(f"feat:{entity}", entity_id)
        if self._client is not None:
            try:
                raw = self._client.get(k)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._memory.get(k, {})

    def set_features(self, entity: str, entity_id: str, features: dict) -> None:
        k = self._key(f"feat:{entity}", entity_id)
        if self._client is not None:
            try:
                self._client.setex(k, self.ttl, json.dumps(features))
                return
            except Exception:
                pass
        self._memory[k] = features

    # ---- Audience segments ----

    def add_user_to_segment(self, user_id: str, segment_id: str) -> None:
        k = self._key("seg", segment_id)
        if self._client is not None:
            try:
                self._client.sadd(k, user_id)
                return
            except Exception:
                pass
        self._memory.setdefault(k, set()).add(user_id)

    def get_user_segments(self, user_id: str) -> list[str]:
        # SCAN-based reverse lookup. Fine for the demo. Production should
        # maintain an inverted index keyed by user_id to avoid the O(N) scan.
        out: list[str] = []
        if self._client is not None:
            try:
                for k in self._client.scan_iter(match="seg:*"):
                    if self._client.sismember(k, user_id):
                        out.append(k.decode().split(":", 1)[1])
                return out
            except Exception:
                pass
        for k, v in self._memory.items():
            if k.startswith("seg:") and isinstance(v, set) and user_id in v:
                out.append(k.split(":", 1)[1])
        return out

    def stats(self) -> dict:
        return {
            "backend": "redis" if self._client is not None else "in-memory",
            "in_memory_keys": len(self._memory),
            "ts": time.time(),
        }
