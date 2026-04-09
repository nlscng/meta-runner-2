"""
Image cache layer for Netrunner card images.

Lazy-fetches card images from NetrunnerDB on first display and stores them
on disk with a configurable TTL.  Uses `diskcache` for TTL tracking and
eviction metadata, while image files live as plain `{code}.jpg` files in the
cache directory for direct serving by Gradio.

Scaling path: swap diskcache.Cache for diskcache.FanoutCache (sharded) or
replace the backend with Redis/S3 behind the same get/put interface.
"""

import logging
import os
from pathlib import Path

import diskcache
import httpx

log = logging.getLogger(__name__)

NRDB_IMAGE_URL = "https://card-images.netrunnerdb.com/v2/large/{code}.jpg"

# Defaults — override via environment or constructor args
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "card_images")
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
DEFAULT_SIZE_LIMIT_MB = 500  # 500 MB (~2500 images × ~150 KB avg, with headroom)


class ImageCache:
    """Disk-backed image cache with TTL expiry.

    Image files are stored as ``{code}.jpg`` in ``cache_dir`` for direct
    serving.  A diskcache index (in a ``_meta/`` subdirectory) tracks TTL
    and eviction — when an entry expires, both the metadata and the image
    file are cleaned up.

    Parameters
    ----------
    cache_dir : str | Path
        Directory for cached image files.  Created automatically.
    ttl : int
        Time-to-live in seconds for each cached image.
    size_limit_mb : int
        Maximum metadata cache size in bytes (images on disk are managed
        separately via eviction callbacks).
    """

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        ttl: int = DEFAULT_TTL_SECONDS,
        size_limit_mb: int = DEFAULT_SIZE_LIMIT_MB,
    ):
        self._cache_dir = Path(cache_dir).resolve()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl
        # Metadata-only cache in a subdirectory to avoid polluting the image dir
        self._meta = diskcache.Cache(
            str(self._cache_dir / "_meta"),
            size_limit=size_limit_mb * 1024 * 1024,
            eviction_policy="least-recently-used",
        )

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_image_path(self, code: str) -> str | None:
        """Return a local file path for the card image, fetching if needed.

        Returns ``None`` if the image could not be fetched (network error,
        404, etc.).  The caller should fall back to the remote URL in that
        case.
        """
        img_path = self._image_file(code)

        # Check metadata for TTL validity
        if self._meta.get(code) is not None and img_path.exists():
            return str(img_path)

        # Stale or missing — clean up and re-fetch
        img_path.unlink(missing_ok=True)

        image_bytes = self._fetch(code)
        if image_bytes is None:
            return None

        img_path.write_bytes(image_bytes)
        self._meta.set(code, True, expire=self._ttl)
        return str(img_path)

    def get_url(self, code: str) -> str:
        """Return a serveable URL — local path if cached, remote otherwise."""
        local = self.get_image_path(code)
        if local and os.path.exists(local):
            return local
        return NRDB_IMAGE_URL.format(code=code)

    def warm(self, codes: list[str]) -> dict[str, bool]:
        """Pre-fetch a batch of images.  Returns {code: success}."""
        results = {}
        for code in codes:
            results[code] = self.get_image_path(code) is not None
        return results

    def evict(self, code: str) -> bool:
        """Remove a single entry.  Returns True if it existed."""
        existed = self._meta.delete(code)
        self._image_file(code).unlink(missing_ok=True)
        return existed

    def clear(self) -> int:
        """Drop all cached images. Returns count of evicted entries."""
        count = len(self._meta)
        self._meta.clear()
        # Remove all .jpg files in the cache directory
        for jpg in self._cache_dir.glob("*.jpg"):
            jpg.unlink(missing_ok=True)
        return count

    def stats(self) -> dict:
        """Cache health summary."""
        jpg_files = list(self._cache_dir.glob("*.jpg"))
        total_bytes = sum(f.stat().st_size for f in jpg_files)
        return {
            "entries": len(self._meta),
            "images_on_disk": len(jpg_files),
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "cache_dir": str(self._cache_dir),
            "ttl_days": round(self._ttl / 86400, 1),
        }

    def close(self):
        self._meta.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _image_file(self, code: str) -> Path:
        """Predictable path for a card image."""
        return self._cache_dir / f"{code}.jpg"

    def _fetch(self, code: str) -> bytes | None:
        """Download card image from NRDB.  Returns bytes or None."""
        url = NRDB_IMAGE_URL.format(code=code)
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                log.warning("Unexpected content-type for %s: %s", code, content_type)
                return None
            return resp.content
        except httpx.HTTPStatusError as exc:
            log.warning("HTTP %s fetching image for card %s", exc.response.status_code, code)
            return None
        except httpx.RequestError as exc:
            log.warning("Network error fetching image for card %s: %s", code, exc)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton for simple usage
# ---------------------------------------------------------------------------
_default_cache: ImageCache | None = None


def get_image_cache(
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    ttl: int = DEFAULT_TTL_SECONDS,
    size_limit_mb: int = DEFAULT_SIZE_LIMIT_MB,
) -> ImageCache:
    """Return (and lazily create) the module-level ImageCache singleton."""
    global _default_cache
    if _default_cache is None:
        _default_cache = ImageCache(
            cache_dir=cache_dir, ttl=ttl, size_limit_mb=size_limit_mb
        )
    return _default_cache
