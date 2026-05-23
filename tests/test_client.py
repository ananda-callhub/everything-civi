"""Tests for client retry/rate-limiting behavior and config defaults."""
from __future__ import annotations

import asyncio
import os

import pytest

from everything_civi.client import CiviCRMAPIError, CiviCRMClient
from everything_civi.config import CiviCRMConfig
from tests.conftest import MockCiviCRMClient


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_config_defaults():
    """CiviCRMConfig has the expected new fields with correct defaults."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        assert config.max_retries == 2
        assert config.retry_delay == 1.0
        assert config.max_concurrent == 5
        assert config.timeout == 30
        assert config.verify_ssl is True
        assert config.base_url == "https://test.example.com"
        assert config.api_key == "test-key"
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


def test_config_env_override():
    """CiviCRMConfig picks up overrides from environment variables."""
    os.environ["CIVICRM_BASE_URL"] = "https://override.example.com"
    os.environ["CIVICRM_API_KEY"] = "override-key"
    os.environ["CIVICRM_MAX_RETRIES"] = "5"
    os.environ["CIVICRM_RETRY_DELAY"] = "2.5"
    os.environ["CIVICRM_MAX_CONCURRENT"] = "10"
    os.environ["CIVICRM_TIMEOUT"] = "60"
    try:
        config = CiviCRMConfig()
        assert config.max_retries == 5
        assert config.retry_delay == 2.5
        assert config.max_concurrent == 10
        assert config.timeout == 60
    finally:
        for key in [
            "CIVICRM_BASE_URL", "CIVICRM_API_KEY",
            "CIVICRM_MAX_RETRIES", "CIVICRM_RETRY_DELAY",
            "CIVICRM_MAX_CONCURRENT", "CIVICRM_TIMEOUT",
        ]:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Client semaphore lazy initialization
# ---------------------------------------------------------------------------

def test_client_semaphore_lazy_init():
    """CiviCRMClient creates semaphore lazily, not at construction time."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        assert client._semaphore is None  # not created yet
        sem = client._get_semaphore()
        assert sem is not None
        assert isinstance(sem, asyncio.Semaphore)
        assert client._semaphore is sem  # cached
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


def test_client_http_client_lazy_init():
    """CiviCRMClient creates the httpx client lazily."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        assert client._client is None  # not created yet
        http_client = client._get_client()
        assert http_client is not None
        assert client._client is http_client  # cached
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


def test_client_stores_config_values():
    """CiviCRMClient stores retry and concurrency config from CiviCRMConfig."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_MAX_RETRIES"] = "4"
    os.environ["CIVICRM_RETRY_DELAY"] = "0.5"
    os.environ["CIVICRM_MAX_CONCURRENT"] = "8"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        assert client._max_retries == 4
        assert client._retry_delay == 0.5
        assert client._max_concurrent == 8
    finally:
        for key in [
            "CIVICRM_BASE_URL", "CIVICRM_API_KEY",
            "CIVICRM_MAX_RETRIES", "CIVICRM_RETRY_DELAY",
            "CIVICRM_MAX_CONCURRENT",
        ]:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Client close lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_close():
    """CiviCRMClient.close() sets _client back to None."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        # Force lazy init of httpx client
        _ = client._get_client()
        assert client._client is not None
        await client.close()
        assert client._client is None
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


@pytest.mark.asyncio
async def test_client_context_manager():
    """CiviCRMClient works as async context manager and closes on exit."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        async with CiviCRMClient(config) as client:
            _ = client._get_client()
            assert client._client is not None
        # After exiting context, client should be closed
        assert client._client is None
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


# ---------------------------------------------------------------------------
# MockCiviCRMClient health_check method
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_health_check_ok(mock_client: MockCiviCRMClient):
    """MockCiviCRMClient.health_check returns ok when System.check succeeds."""
    mock_client.set_response("System", "check", {
        "values": [{"name": "checkVersion", "severity_id": 1}],
    })
    result = await mock_client.health_check()
    assert result["status"] == "ok"
    assert len(result["checks"]) == 1
    assert result["checks"][0]["name"] == "checkVersion"


@pytest.mark.asyncio
async def test_mock_health_check_error(mock_client: MockCiviCRMClient):
    """MockCiviCRMClient.health_check returns error when System.check fails."""
    mock_client.set_error("System", "check", "Connection refused")
    result = await mock_client.health_check()
    assert result["status"] == "error"
    assert "Connection refused" in result["error"]


# ---------------------------------------------------------------------------
# CiviCRMAPIError
# ---------------------------------------------------------------------------

def test_api_error_attributes():
    """CiviCRMAPIError stores error_message and error_code."""
    err = CiviCRMAPIError("Something broke", 500)
    assert err.error_message == "Something broke"
    assert err.error_code == 500
    assert "500" in str(err)
    assert "Something broke" in str(err)


def test_api_error_default_code():
    """CiviCRMAPIError defaults error_code to 0."""
    err = CiviCRMAPIError("oops")
    assert err.error_code == 0
