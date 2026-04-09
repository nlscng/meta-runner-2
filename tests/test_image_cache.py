"""Tests for src/image_cache.py — disk-backed card image caching."""

import os

import pytest
import httpx

from src.image_cache import ImageCache, NRDB_IMAGE_URL


FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG header + padding
FAKE_REQUEST = httpx.Request("GET", "https://card-images.netrunnerdb.com/v2/large/test.jpg")


def _ok_response(content=FAKE_JPEG, content_type="image/jpeg"):
    """Build a mock 200 response with a request attached (httpx requires it)."""
    return httpx.Response(
        200, content=content,
        headers={"content-type": content_type},
        request=FAKE_REQUEST,
    )


@pytest.fixture()
def cache(tmp_path):
    """Fresh ImageCache backed by a temp directory."""
    c = ImageCache(cache_dir=tmp_path / "card_images", ttl=3600, size_limit_mb=10)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Core get / set / evict
# ---------------------------------------------------------------------------

class TestCacheBasics:
    def test_get_url_falls_back_to_remote_on_network_error(self, cache, monkeypatch):
        """When fetch fails, get_url returns the remote NRDB URL."""
        def _fail(*args, **kwargs):
            raise httpx.ConnectError("offline")
        monkeypatch.setattr(httpx, "get", _fail)

        url = cache.get_url("01001")
        assert url == NRDB_IMAGE_URL.format(code="01001")

    def test_get_image_path_returns_none_on_network_error(self, cache, monkeypatch):
        def _fail(*args, **kwargs):
            raise httpx.ConnectError("offline")
        monkeypatch.setattr(httpx, "get", _fail)

        assert cache.get_image_path("01001") is None

    def test_successful_fetch_caches_and_returns_path(self, cache, monkeypatch):
        """Happy path: image fetched, cached, returned as local path."""
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        path = cache.get_image_path("01005")
        assert path is not None
        assert os.path.exists(path)
        assert path.endswith("01005.jpg")
        assert "/images/" in path
        with open(path, "rb") as f:
            assert f.read() == FAKE_JPEG

    def test_second_get_uses_cache_no_fetch(self, cache, monkeypatch):
        """Second request for same code should not hit the network."""
        resp = _ok_response()
        call_count = 0
        def _counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp
        monkeypatch.setattr(httpx, "get", _counting_get)

        cache.get_image_path("01005")
        assert call_count == 1

        cache.get_image_path("01005")
        assert call_count == 1  # no second fetch

    def test_evict_removes_entry(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        cache.get_image_path("01005")
        assert cache.evict("01005") is True
        # After eviction, cache miss — would need to re-fetch
        assert cache.evict("01005") is False

    def test_clear_removes_all(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        cache.get_image_path("01001")
        cache.get_image_path("01002")
        assert cache.stats()["entries"] == 2

        cleared = cache.clear()
        assert cleared == 2
        assert cache.stats()["entries"] == 0


# ---------------------------------------------------------------------------
# TTL (deterministic via diskcache expiry, no sleeps)
# ---------------------------------------------------------------------------

class TestTTL:
    def test_expired_entry_triggers_refetch(self, cache, monkeypatch):
        """After metadata is expired, the cache should re-fetch on next access."""
        resp = _ok_response()
        call_count = 0
        def _counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp
        monkeypatch.setattr(httpx, "get", _counting_get)

        cache.get_image_path("01001")
        assert call_count == 1

        # Simulate TTL expiry by deleting metadata directly
        cache._meta.delete("01001")

        cache.get_image_path("01001")
        assert call_count == 2  # had to re-fetch

    def test_expired_entry_replaces_stale_file(self, cache, monkeypatch):
        """Image file on disk is replaced with fresh data after TTL expiry."""
        old_data = b"\xff\xd8\xff\xe0" + b"\x01" * 50
        new_data = b"\xff\xd8\xff\xe0" + b"\x02" * 50
        call_count = 0

        def _get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            data = old_data if call_count == 1 else new_data
            return _ok_response(content=data)

        monkeypatch.setattr(httpx, "get", _get)

        path = cache.get_image_path("01001")
        with open(path, "rb") as f:
            assert f.read() == old_data

        # Simulate TTL expiry
        cache._meta.delete("01001")

        path = cache.get_image_path("01001")
        with open(path, "rb") as f:
            assert f.read() == new_data  # file was refreshed, not stale


# ---------------------------------------------------------------------------
# Stale file resilience
# ---------------------------------------------------------------------------

class TestStaleResilience:
    def test_stale_file_served_when_refresh_fails(self, cache, monkeypatch):
        """If a stale file exists but refresh fails, serve the stale file."""
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        path = cache.get_image_path("01001")
        assert path is not None
        assert os.path.exists(path)

        # Expire metadata
        cache._meta.delete("01001")

        # Network goes down
        def _fail(*args, **kwargs):
            raise httpx.ConnectError("offline")
        monkeypatch.setattr(httpx, "get", _fail)

        # Should serve stale file instead of returning None
        result = cache.get_image_path("01001")
        assert result is not None
        assert os.path.exists(result)
        with open(result, "rb") as f:
            assert f.read() == FAKE_JPEG


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_http_404_returns_none(self, cache, monkeypatch):
        def _get(*args, **kwargs):
            r = httpx.Response(404, request=FAKE_REQUEST)
            r.raise_for_status()
        monkeypatch.setattr(httpx, "get", _get)

        assert cache.get_image_path("99999") is None

    def test_non_image_content_type_rejected(self, cache, monkeypatch):
        resp = _ok_response(content=b"<html>not an image</html>", content_type="text/html")
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        assert cache.get_image_path("01001") is None

    def test_timeout_returns_none(self, cache, monkeypatch):
        def _timeout(*args, **kwargs):
            raise httpx.ReadTimeout("timed out")
        monkeypatch.setattr(httpx, "get", _timeout)

        assert cache.get_image_path("01001") is None


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------

class TestPathSafety:
    def test_rejects_path_traversal(self, cache):
        with pytest.raises(ValueError, match="Invalid card code"):
            cache.get_image_path("../etc/passwd")

    def test_rejects_slash_in_code(self, cache):
        with pytest.raises(ValueError, match="Invalid card code"):
            cache.get_image_path("01001/../../etc")

    def test_accepts_valid_codes(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)
        # NRDB codes are typically numeric, but some include letters
        for code in ["01001", "21001", "alt-art-01"]:
            assert cache.get_image_path(code) is not None


# ---------------------------------------------------------------------------
# Prune orphaned files
# ---------------------------------------------------------------------------

class TestPrune:
    def test_prune_removes_orphaned_images(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        cache.get_image_path("01001")
        cache.get_image_path("01002")

        # Expire one entry's metadata, leaving the file orphaned
        cache._meta.delete("01001")

        removed = cache.prune()
        assert removed == 1
        assert not (cache.images_dir / "01001.jpg").exists()
        assert (cache.images_dir / "01002.jpg").exists()


# ---------------------------------------------------------------------------
# Stats & warm
# ---------------------------------------------------------------------------

class TestStatsAndWarm:
    def test_stats_reports_cache_state(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        s = cache.stats()
        assert s["entries"] == 0
        assert s["ttl_days"] == pytest.approx(1 / 24, abs=0.1)  # 3600s ≈ 0.04 days

        cache.get_image_path("01001")
        s = cache.stats()
        assert s["entries"] == 1
        assert s["images_on_disk"] == 1
        assert s["size_mb"] >= 0  # tiny test image rounds to 0.0

    def test_warm_prefetches_batch(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        results = cache.warm(["01001", "01002", "01003"])
        assert all(results.values())
        assert cache.stats()["entries"] == 3


# ---------------------------------------------------------------------------
# get_url helper
# ---------------------------------------------------------------------------

class TestGetUrl:
    def test_returns_local_path_when_cached(self, cache, monkeypatch):
        resp = _ok_response()
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: resp)

        url = cache.get_url("01005")
        assert "01005.jpg" in url
        assert not url.startswith("http")

    def test_returns_remote_url_when_not_cached(self, cache, monkeypatch):
        def _fail(*args, **kwargs):
            raise httpx.ConnectError("offline")
        monkeypatch.setattr(httpx, "get", _fail)

        url = cache.get_url("01005")
        assert url.startswith("https://")
