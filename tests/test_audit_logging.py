"""Tests for audit logging: JSON formatter, setup_logging, and client audit records."""
from __future__ import annotations

import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from everything_civi.client import CiviCRMAPIError, CiviCRMClient
from everything_civi.config import CiviCRMConfig
from everything_civi.logging_config import JSONFormatter, setup_logging


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_output():
    """JSONFormatter produces valid JSON with expected fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="test message", args=(), exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert data["message"] == "test message"
    assert data["level"] == "INFO"
    assert "timestamp" in data
    assert data["logger"] == "test"


def test_json_formatter_extra_fields():
    """JSONFormatter includes extra fields in output."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="api4_call", args=(), exc_info=None,
    )
    record.entity = "Contact"
    record.action = "get"
    record.duration_ms = 42.5
    output = formatter.format(record)
    data = json.loads(output)
    assert data["entity"] == "Contact"
    assert data["action"] == "get"
    assert data["duration_ms"] == 42.5


def test_json_formatter_exception_included():
    """JSONFormatter includes exception info when present."""
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="something failed", args=(), exc_info=exc_info,
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert "exception" in data
    assert "ValueError" in data["exception"]
    assert "boom" in data["exception"]


def test_json_formatter_single_line():
    """JSONFormatter output is always a single line (no embedded newlines outside the JSON string)."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="line one\nline two", args=(), exc_info=None,
    )
    output = formatter.format(record)
    # json.dumps escapes newlines inside strings, so the output line count should be 1
    assert output.count("\n") == 0
    data = json.loads(output)
    assert "line one\nline two" in data["message"]


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_pkg_logger():
    """Save and restore everything_civi logger state around each test."""
    pkg = logging.getLogger("everything_civi")
    orig_level = pkg.level
    orig_handlers = pkg.handlers[:]
    orig_propagate = pkg.propagate
    yield pkg
    pkg.setLevel(orig_level)
    pkg.handlers = orig_handlers
    pkg.propagate = orig_propagate


def test_setup_logging_configures_level(_restore_pkg_logger):
    """setup_logging sets the package logger level."""
    setup_logging("DEBUG")
    assert _restore_pkg_logger.level == logging.DEBUG


def test_setup_logging_uses_json_formatter(_restore_pkg_logger):
    """setup_logging attaches a handler with JSONFormatter."""
    setup_logging("WARNING")
    assert len(_restore_pkg_logger.handlers) == 1
    assert isinstance(_restore_pkg_logger.handlers[0].formatter, JSONFormatter)


def test_setup_logging_no_duplicate_handlers(_restore_pkg_logger):
    """Calling setup_logging twice does not duplicate handlers."""
    setup_logging("INFO")
    setup_logging("INFO")
    assert len(_restore_pkg_logger.handlers) == 1


# ---------------------------------------------------------------------------
# Config audit_log field
# ---------------------------------------------------------------------------


def test_config_audit_log_defaults_to_true():
    """CiviCRMConfig.audit_log defaults to True."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        assert config.audit_log is True
    finally:
        os.environ.pop("CIVICRM_BASE_URL", None)
        os.environ.pop("CIVICRM_API_KEY", None)


def test_config_audit_log_env_override():
    """CiviCRMConfig.audit_log can be set via environment variable."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_AUDIT_LOG"] = "false"
    try:
        config = CiviCRMConfig()
        assert config.audit_log is False
    finally:
        for k in ["CIVICRM_BASE_URL", "CIVICRM_API_KEY", "CIVICRM_AUDIT_LOG"]:
            os.environ.pop(k, None)


def test_config_log_level_default():
    """CiviCRMConfig.log_level defaults to INFO."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        assert config.log_level == "INFO"
    finally:
        os.environ.pop("CIVICRM_BASE_URL", None)
        os.environ.pop("CIVICRM_API_KEY", None)


# ---------------------------------------------------------------------------
# Fixtures for client audit log tests
# ---------------------------------------------------------------------------


def _make_mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    content_type: str = "application/json",
) -> MagicMock:
    """Create a mock httpx response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {"content-type": content_type}
    mock_response.json.return_value = json_data or {"values": [{"id": 1}]}
    mock_response.raise_for_status = MagicMock()
    return mock_response


@pytest.fixture
def audit_client():
    """Create a CiviCRMClient with audit logging enabled."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_AUDIT_LOG"] = "true"
    os.environ["CIVICRM_MAX_RETRIES"] = "0"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        yield client
    finally:
        for k in ["CIVICRM_BASE_URL", "CIVICRM_API_KEY", "CIVICRM_AUDIT_LOG", "CIVICRM_MAX_RETRIES"]:
            os.environ.pop(k, None)


@pytest.fixture
def no_audit_client():
    """Create a CiviCRMClient with audit logging disabled."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_AUDIT_LOG"] = "false"
    os.environ["CIVICRM_MAX_RETRIES"] = "0"
    try:
        config = CiviCRMConfig()
        client = CiviCRMClient(config)
        yield client
    finally:
        for k in ["CIVICRM_BASE_URL", "CIVICRM_API_KEY", "CIVICRM_AUDIT_LOG", "CIVICRM_MAX_RETRIES"]:
            os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# Client audit log tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_call_produces_audit_log(audit_client, caplog):
    """Successful api4 call produces an audit log record with expected fields."""
    mock_response = _make_mock_response(json_data={"values": [{"id": 1}]})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Contact", "get", {"select": ["id", "display_name"], "limit": 25})

    # Find the audit log record
    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1, f"Expected audit log record, got: {[r.name for r in caplog.records]}"

    record = audit_records[0]
    assert getattr(record, "entity", None) == "Contact"
    assert getattr(record, "action", None) == "get"
    assert getattr(record, "status", None) == "success"
    assert isinstance(getattr(record, "duration_ms", None), (int, float))
    assert getattr(record, "duration_ms") >= 0


@pytest.mark.asyncio
async def test_error_call_produces_audit_log(audit_client, caplog):
    """Failed api4 call produces an audit log record with status=error."""
    import httpx

    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            with pytest.raises(CiviCRMAPIError):
                await audit_client.api4("Event", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1, f"Expected audit log record on error, got: {[r.name for r in caplog.records]}"

    record = audit_records[0]
    assert getattr(record, "entity", None) == "Event"
    assert getattr(record, "action", None) == "get"
    assert getattr(record, "status", None) == "error"
    assert isinstance(getattr(record, "duration_ms", None), (int, float))


@pytest.mark.asyncio
async def test_audit_log_disabled_skips_logging(no_audit_client, caplog):
    """With audit_log=False, no audit log records are produced."""
    mock_response = _make_mock_response(json_data={"values": []})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    with patch.object(no_audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await no_audit_client.api4("Activity", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) == 0, (
        f"Expected no audit records when audit_log=False, got {len(audit_records)}"
    )


@pytest.mark.asyncio
async def test_param_keys_logged_not_values(audit_client, caplog):
    """Audit log records param_keys (list of keys), NOT full param values."""
    mock_response = _make_mock_response(json_data={"values": [{"id": 1}]})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    params = {
        "select": ["id", "title", "start_date"],
        "where": [["id", "=", 42]],
        "limit": 10,
    }

    # Use a non-sensitive entity (Event) so param_keys are logged.
    # Sensitive entities (Contact, Email, etc.) intentionally suppress param_keys.
    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Event", "get", params)

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1

    record = audit_records[0]
    param_keys = getattr(record, "param_keys", None)
    assert param_keys is not None, "Expected param_keys in audit log record"
    # param_keys should be a list of the parameter keys
    assert isinstance(param_keys, list)
    assert set(param_keys) == {"select", "where", "limit"}
    # Verify full param values are NOT in the record
    assert not hasattr(record, "params"), "Full params dict should NOT be logged"


@pytest.mark.asyncio
async def test_sensitive_entity_suppresses_param_keys(audit_client, caplog):
    """Sensitive entities (Contact, Email, etc.) suppress param_keys in audit log."""
    mock_response = _make_mock_response(json_data={"values": [{"id": 1}]})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    params = {"select": ["id", "first_name", "email"], "limit": 10}

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Contact", "get", params)

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1

    record = audit_records[0]
    # For sensitive entities, param_keys should be None (suppressed)
    param_keys = getattr(record, "param_keys", "MISSING")
    assert param_keys is None, (
        f"Expected param_keys=None for sensitive entity Contact, got {param_keys}"
    )


@pytest.mark.asyncio
async def test_audit_log_with_no_params(audit_client, caplog):
    """Audit log handles api4 calls with no params gracefully."""
    mock_response = _make_mock_response(json_data={"values": []})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Entity", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1

    record = audit_records[0]
    assert getattr(record, "entity", None) == "Entity"
    assert getattr(record, "action", None) == "get"
    # param_keys should be empty list or None when no params passed
    param_keys = getattr(record, "param_keys", None)
    assert param_keys is None or param_keys == []


@pytest.mark.asyncio
async def test_audit_log_records_message(audit_client, caplog):
    """Audit log record message is 'api4_call' for successful calls."""
    mock_response = _make_mock_response(json_data={"values": []})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Contact", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    assert len(audit_records) >= 1
    assert audit_records[0].message == "api4_call"


@pytest.mark.asyncio
async def test_audit_log_error_level_is_warning(audit_client, caplog):
    """Error audit log records are at WARNING level."""
    import httpx

    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            with pytest.raises(CiviCRMAPIError):
                await audit_client.api4("Contact", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    error_records = [r for r in audit_records if getattr(r, "status", None) == "error"]
    assert len(error_records) >= 1
    assert error_records[0].levelno == logging.WARNING


@pytest.mark.asyncio
async def test_audit_log_success_level_is_info(audit_client, caplog):
    """Success audit log records are at INFO level."""
    mock_response = _make_mock_response(json_data={"values": []})
    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    with patch.object(audit_client, "_get_client", return_value=mock_http_client):
        with caplog.at_level(logging.DEBUG, logger="everything_civi.audit"):
            await audit_client.api4("Contact", "get")

    audit_records = [r for r in caplog.records if r.name == "everything_civi.audit"]
    success_records = [r for r in audit_records if getattr(r, "status", None) == "success"]
    assert len(success_records) >= 1
    assert success_records[0].levelno == logging.INFO
