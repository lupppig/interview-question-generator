"""Redis-backed cache for generated interview questions.

Lookup order:
1. Exact normalized key  (lowercase, whitespace collapsed)
2. Phonetic key          (Double Metaphone per word)

When a new entry is stored it is written under *both* keys so that
future requests hitting either path get a cache hit.

Redis failures are swallowed — the cache is an optimization,
not a source of truth.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import redis.asyncio as redis
from metaphone import doublemetaphone
from redis.exceptions import RedisError

logger = logging.getLogger("interview_generator")

_EXACT_PREFIX = "iqg:questions:v1:"
_PHONETIC_PREFIX = "iqg:questions:phonetic:v1:"
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_job_title(job_title: str) -> str:
    return _WHITESPACE_RE.sub(" ", job_title).strip().lower()


def phonetic_key(job_title: str) -> str:
    """Build a phonetic cache key from the Double Metaphone of each word."""
    normalized = normalize_job_title(job_title)
    codes: list[str] = []
    for word in normalized.split():
        primary, _ = doublemetaphone(word)
        codes.append(primary or word)
    return _PHONETIC_PREFIX + " ".join(codes)


def _exact_key(job_title: str) -> str:
    return _EXACT_PREFIX + normalize_job_title(job_title)


@dataclass
class CacheResult:
    questions: list[str]
    hit_type: str  # "exact" or "phonetic"


class QuestionCache:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._client: redis.Redis | None = None
        if redis_url:
            try:
                self._client = redis.from_url(redis_url, decode_responses=True)
            except (ValueError, RedisError) as exc:
                logger.warning("cache_init_failed: %s", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def get(self, job_title: str) -> CacheResult | None:
        if not self._client:
            return None

        # 1. Try exact normalized match first.
        exact = await self._fetch(_exact_key(job_title))
        if exact is not None:
            return CacheResult(questions=exact, hit_type="exact")

        # 2. Fall back to phonetic match.
        phon = await self._fetch(phonetic_key(job_title))
        if phon is not None:
            return CacheResult(questions=phon, hit_type="phonetic")

        return None

    async def set(self, job_title: str, questions: list[str]) -> None:
        """Store questions under both the exact and phonetic keys."""
        if not self._client:
            return
        value = json.dumps(questions)
        await self._store(_exact_key(job_title), value)
        await self._store(phonetic_key(job_title), value)

    # --- internal helpers ---------------------------------------------------

    async def _fetch(self, key: str) -> list[str] | None:
        try:
            raw = await self._client.get(key)  # type: ignore[union-attr]
        except RedisError as exc:
            logger.warning("cache_get_failed: key=%s err=%s", key, exc)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list) or not all(isinstance(q, str) for q in data):
            return None
        return data

    async def _store(self, key: str, value: str) -> None:
        try:
            await self._client.set(key, value, ex=self._ttl)  # type: ignore[union-attr]
        except RedisError as exc:
            logger.warning("cache_set_failed: key=%s err=%s", key, exc)
