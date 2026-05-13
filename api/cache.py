"""Redis-backed cache for generated interview questions.

The key is the job title normalized (lowercase, whitespace collapsed) so that
"Software Engineer", "software engineer", and " software  engineer " all hit
the same entry. Redis failures are swallowed — the cache is an optimization,
not a source of truth.
"""

from __future__ import annotations

import json
import logging
import re

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger("interview_generator")

_KEY_PREFIX = "iqg:questions:v1:"
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_job_title(job_title: str) -> str:
    return _WHITESPACE_RE.sub(" ", job_title).strip().lower()


def _cache_key(job_title: str) -> str:
    return _KEY_PREFIX + normalize_job_title(job_title)


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

    async def get(self, job_title: str) -> list[str] | None:
        if not self._client:
            return None
        try:
            raw = await self._client.get(_cache_key(job_title))
        except RedisError as exc:
            logger.warning("cache_get_failed: %s", exc)
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

    async def set(self, job_title: str, questions: list[str]) -> None:
        if not self._client:
            return
        try:
            await self._client.set(
                _cache_key(job_title),
                json.dumps(questions),
                ex=self._ttl,
            )
        except RedisError as exc:
            logger.warning("cache_set_failed: %s", exc)
