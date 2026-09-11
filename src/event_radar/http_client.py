"""Polite HTTP: timeouts, retries, per-host delay, file cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from event_radar.config import DATA_DIR


class FetchError(RuntimeError):
    def __init__(self, url: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url
        self.status_code = status_code


class HttpFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_sec: float = 25,
        retries: int = 3,
        per_host_delay_sec: float = 1.2,
        cache_ttl_sec: int = 3600,
        cache_dir: Path | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_sec = timeout_sec
        self.retries = retries
        self.per_host_delay_sec = per_host_delay_sec
        self.cache_ttl_sec = cache_ttl_sec
        self.cache_dir = cache_dir or (DATA_DIR / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_host_at: dict[str, float] = {}

    def get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        ttl_sec: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        ttl = self.cache_ttl_sec if ttl_sec is None else ttl_sec
        cache_path = self._cache_path(url)
        if ttl > 0 and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < ttl:
                return cache_path.read_bytes()

        merged = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
        }
        if headers:
            merged.update(headers)
        if extra_headers:
            merged.update(extra_headers)

        self._respect_host(url)
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_sec, follow_redirects=True) as client:
                    response = client.get(url, headers=merged)
                if response.status_code in {429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.6 * (2**attempt)
                    time.sleep(delay)
                    last_exc = FetchError(url, f"HTTP {response.status_code}", response.status_code)
                    continue
                if response.status_code >= 400:
                    raise FetchError(url, f"HTTP {response.status_code}", response.status_code)
                cache_path.write_bytes(response.content)
                return response.content
            except httpx.HTTPError as exc:
                last_exc = FetchError(url, str(exc))
                time.sleep(0.6 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.get_bytes(url, **kwargs).decode("utf-8", errors="replace")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        payload = self.get_bytes(url, **kwargs)
        return json.loads(payload.decode("utf-8"))

    def _respect_host(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_host_at.get(host)
        now = time.time()
        if last is not None:
            wait = self.per_host_delay_sec - (now - last)
            if wait > 0:
                time.sleep(wait)
        self._last_host_at[host] = time.time()

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{digest}.bin"
