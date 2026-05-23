"""Unit tests for admin tools using MockCiviCRMClient."""
from __future__ import annotations

import json

import pytest

from mcp.server.fastmcp import FastMCP

from everything_civi.admin_tools import register_admin_tools
from tests.conftest import MockCiviCRMClient


@pytest.fixture
def tools(mock_client: MockCiviCRMClient) -> dict:
    """Register admin tools and return them as a name->function dict."""
    mcp = FastMCP("test")
    register_admin_tools(mcp, mock_client)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


@pytest.mark.asyncio
async def test_system_status_ok(mock_client: MockCiviCRMClient, tools):
    """System status returns connection=ok with version info when healthy."""
    mock_client.set_response("System", "check", {
        "values": [
            {"name": "checkVersion", "severity_id": 1, "message": "Up to date"},
        ],
    })
    mock_client.set_response("System", "get", {
        "values": [
            {
                "version": "5.69.0",
                "uf": "WordPress",
                "baseUrl": "https://civi.example.com",
            },
        ],
    })

    result = json.loads(await tools["civicrm_system_status"]())
    assert result["connection"] == "ok"
    assert result["civicrm_version"] == "5.69.0"
    assert result["cms"] == "WordPress"
    assert result["base_url"] == "https://civi.example.com"
    # No warnings key since severity_id < 3
    assert "warnings" not in result


@pytest.mark.asyncio
async def test_system_status_with_warnings(mock_client: MockCiviCRMClient, tools):
    """System status includes warnings when severity >= 3."""
    mock_client.set_response("System", "check", {
        "values": [
            {"name": "checkExtensions", "severity_id": 3, "message": "Extension outdated"},
            {"name": "checkVersion", "severity_id": 1, "message": "Up to date"},
        ],
    })
    mock_client.set_response("System", "get", {
        "values": [{"version": "5.69.0", "uf": "Drupal", "baseUrl": "https://civi.example.com"}],
    })

    result = json.loads(await tools["civicrm_system_status"]())
    assert result["connection"] == "ok"
    assert "warnings" in result
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["name"] == "checkExtensions"


@pytest.mark.asyncio
async def test_system_status_connection_error(mock_client: MockCiviCRMClient, tools):
    """System status returns connection=error when health check fails (not a crash)."""
    mock_client.set_error("System", "check", "Connection refused")

    result = json.loads(await tools["civicrm_system_status"]())
    assert result["connection"] == "error"
    assert "error" in result


@pytest.mark.asyncio
async def test_system_status_version_api_error(mock_client: MockCiviCRMClient, tools):
    """System status still works when System.get fails (version info is optional)."""
    mock_client.set_response("System", "check", {"values": []})
    mock_client.set_error("System", "get", "Permission denied")

    result = json.loads(await tools["civicrm_system_status"]())
    assert result["connection"] == "ok"
    # Version info should be None since System.get failed
    assert result["civicrm_version"] is None


@pytest.mark.asyncio
async def test_system_flush(mock_client: MockCiviCRMClient, tools):
    """System flush returns status=ok on success."""
    mock_client.set_response("System", "flush", {"values": []})

    result = json.loads(await tools["civicrm_system_flush"]())
    assert result["status"] == "ok"
    assert "completed" in result["message"]

    # Verify the API call was made
    assert mock_client.calls[0] == ("System", "flush", {})


@pytest.mark.asyncio
async def test_system_flush_error(mock_client: MockCiviCRMClient, tools):
    """System flush returns error string when API fails."""
    mock_client.set_error("System", "flush", "Permission denied")

    result = await tools["civicrm_system_flush"]()
    assert "Error flushing cache" in result
    assert "Permission denied" in result
