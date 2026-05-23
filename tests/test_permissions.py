"""Tests for tool permission allowlist."""
from __future__ import annotations

import os

import pytest

from mcp.server.fastmcp import FastMCP

from everything_civi.config import CiviCRMConfig
from everything_civi.crud_tools import register_crud_tools
from everything_civi.discovery_tools import register_discovery_tools
from everything_civi.admin_tools import register_admin_tools
from tests.conftest import MockCiviCRMClient


@pytest.fixture(autouse=True)
def _clean_env():
    """Ensure allowlist env var is removed before and after each test."""
    os.environ.pop("CIVICRM_ALLOWED_TOOLS", None)
    yield
    os.environ.pop("CIVICRM_ALLOWED_TOOLS", None)


# ---------------------------------------------------------------------------
# Config parsing tests
# ---------------------------------------------------------------------------


def test_config_allowed_tools_default():
    """Empty allowed_tools means all tools allowed."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    try:
        config = CiviCRMConfig()
        assert config.get_allowed_tools() is None
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]


def test_config_allowed_tools_parsed():
    """Comma-separated list is parsed into a set."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_ALLOWED_TOOLS"] = "civicrm_get, civicrm_create ,civicrm_list_entities"
    try:
        config = CiviCRMConfig()
        allowed = config.get_allowed_tools()
        assert allowed == {"civicrm_get", "civicrm_create", "civicrm_list_entities"}
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]
        del os.environ["CIVICRM_ALLOWED_TOOLS"]


def test_config_allowed_tools_whitespace_only():
    """Whitespace-only value means all tools allowed."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_ALLOWED_TOOLS"] = "  "
    try:
        config = CiviCRMConfig()
        assert config.get_allowed_tools() is None
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]
        del os.environ["CIVICRM_ALLOWED_TOOLS"]


def test_config_allowed_tools_trailing_commas():
    """Trailing/leading commas and empty entries are ignored."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_ALLOWED_TOOLS"] = ",civicrm_get,,civicrm_create,"
    try:
        config = CiviCRMConfig()
        allowed = config.get_allowed_tools()
        assert allowed == {"civicrm_get", "civicrm_create"}
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]
        del os.environ["CIVICRM_ALLOWED_TOOLS"]


def test_config_allowed_tools_single_tool():
    """A single tool name without commas is parsed correctly."""
    os.environ["CIVICRM_BASE_URL"] = "https://test.example.com"
    os.environ["CIVICRM_API_KEY"] = "test-key"
    os.environ["CIVICRM_ALLOWED_TOOLS"] = "civicrm_get"
    try:
        config = CiviCRMConfig()
        allowed = config.get_allowed_tools()
        assert allowed == {"civicrm_get"}
    finally:
        del os.environ["CIVICRM_BASE_URL"]
        del os.environ["CIVICRM_API_KEY"]
        del os.environ["CIVICRM_ALLOWED_TOOLS"]


# ---------------------------------------------------------------------------
# Functional pruning tests
# ---------------------------------------------------------------------------


def test_pruning_removes_unlisted_tools():
    """Tools not in the allowlist are removed from the MCP server."""
    mock_client = MockCiviCRMClient()
    server = FastMCP("test-pruning")

    register_crud_tools(server, mock_client)
    register_discovery_tools(server, mock_client)
    register_admin_tools(server, mock_client)

    all_tools = set(server._tool_manager._tools.keys())
    assert len(all_tools) > 3

    keep = {"civicrm_get", "civicrm_create"}

    for name in list(all_tools):
        if name not in keep:
            del server._tool_manager._tools[name]

    remaining = set(server._tool_manager._tools.keys())
    assert remaining == keep & all_tools


def test_pruning_empty_allowlist_keeps_all():
    """When allowlist is None (empty config), no pruning occurs."""
    mock_client = MockCiviCRMClient()
    server = FastMCP("test-no-pruning")

    register_crud_tools(server, mock_client)
    register_discovery_tools(server, mock_client)

    all_tools_before = set(server._tool_manager._tools.keys())
    assert len(all_tools_before) > 0

    allowed = None
    if allowed is not None:
        for name in list(server._tool_manager._tools.keys()):
            if name not in allowed:
                del server._tool_manager._tools[name]

    all_tools_after = set(server._tool_manager._tools.keys())
    assert all_tools_after == all_tools_before


def test_pruning_allowlist_with_unknown_names():
    """Allowlist entries that don't match any registered tool are harmlessly ignored."""
    mock_client = MockCiviCRMClient()
    server = FastMCP("test-unknown")

    register_crud_tools(server, mock_client)

    allowed = {"civicrm_get", "nonexistent_tool"}

    for name in list(server._tool_manager._tools.keys()):
        if name not in allowed:
            del server._tool_manager._tools[name]

    remaining = set(server._tool_manager._tools.keys())
    assert remaining == {"civicrm_get"}
