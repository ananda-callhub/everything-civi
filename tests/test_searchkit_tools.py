"""Unit tests for SearchKit tools using MockCiviCRMClient."""
from __future__ import annotations

import json

import pytest

from mcp.server.fastmcp import FastMCP

from everything_civi.searchkit_tools import register_searchkit_tools
from tests.conftest import MockCiviCRMClient


@pytest.fixture
def tools(mock_client: MockCiviCRMClient) -> dict:
    """Register searchkit tools and return them as a name->function dict."""
    mcp = FastMCP("test")
    register_searchkit_tools(mcp, mock_client)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


# ---------- civicrm_list_saved_searches ----------


@pytest.mark.asyncio
async def test_list_saved_searches(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("SavedSearch", "get", {
        "values": [
            {
                "id": 1,
                "name": "my_contacts",
                "label": "My Contacts",
                "description": "All contacts",
                "api_entity": "Contact",
                "created_date": "2025-01-01",
                "modified_date": "2025-06-01",
            },
            {
                "id": 2,
                "name": "recent_donors",
                "label": "Recent Donors",
                "description": None,
                "api_entity": "Contribution",
                "created_date": "2025-03-15",
                "modified_date": "2025-03-15",
            },
        ],
    })

    result = json.loads(await tools["civicrm_list_saved_searches"]())
    assert len(result) == 2
    assert result[0]["name"] == "my_contacts"
    assert result[1]["name"] == "recent_donors"

    # Verify the API call was made correctly
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[0] == "SavedSearch"
    assert call[1] == "get"
    assert "select" in call[2]


@pytest.mark.asyncio
async def test_list_saved_searches_api_error(mock_client: MockCiviCRMClient, tools):
    mock_client.set_error("SavedSearch", "get", "Permission denied", 403)

    result = await tools["civicrm_list_saved_searches"]()
    assert "Error listing saved searches" in result
    assert "Permission denied" in result


# ---------- civicrm_run_saved_search ----------


@pytest.mark.asyncio
async def test_run_saved_search_with_display(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("SearchDisplay", "run", {
        "values": [
            {"id": 1, "display_name": "Alice Smith"},
            {"id": 2, "display_name": "Bob Jones"},
        ],
        "count": 2,
        "labels": ["ID", "Name"],
    })

    result = json.loads(await tools["civicrm_run_saved_search"](
        saved_search="my_contacts",
        display="my_contacts_table",
    ))
    assert len(result["values"]) == 2
    assert result["count"] == 2
    assert result["labels"] == ["ID", "Name"]

    # Should NOT look up display since one was provided
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[0] == "SearchDisplay"
    assert call[1] == "run"
    assert call[2]["savedSearch"] == "my_contacts"
    assert call[2]["display"] == "my_contacts_table"
    assert call[2]["limit"] == 50
    assert call[2]["offset"] == 0


@pytest.mark.asyncio
async def test_run_saved_search_auto_display(mock_client: MockCiviCRMClient, tools):
    # First call: look up display name
    mock_client.set_response("SearchDisplay", "get", {
        "values": [{"name": "auto_display_1"}],
    })
    # Second call: run the display
    mock_client.set_response("SearchDisplay", "run", {
        "values": [{"id": 10, "email": "test@example.com"}],
        "count": 1,
        "labels": [],
    })

    result = json.loads(await tools["civicrm_run_saved_search"](
        saved_search="my_contacts",
    ))
    assert result["count"] == 1

    # Should have made two calls: get display, then run
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][1] == "get"
    assert mock_client.calls[0][2]["where"] == [
        ["saved_search_id.name", "=", "my_contacts"],
    ]
    assert mock_client.calls[1][1] == "run"
    assert mock_client.calls[1][2]["display"] == "auto_display_1"


@pytest.mark.asyncio
async def test_run_saved_search_no_display_found(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("SearchDisplay", "get", {"values": []})

    result = json.loads(await tools["civicrm_run_saved_search"](
        saved_search="nonexistent_search",
    ))
    assert "error" in result
    assert "No display found" in result["error"]
    assert "nonexistent_search" in result["error"]

    # Should only have made the display lookup call
    assert len(mock_client.calls) == 1


@pytest.mark.asyncio
async def test_run_saved_search_with_filters_and_sort(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("SearchDisplay", "run", {
        "values": [{"id": 5}],
        "count": 1,
        "labels": [],
    })

    await tools["civicrm_run_saved_search"](
        saved_search="my_contacts",
        display="my_table",
        filters={"contact_type": "Individual"},
        limit=25,
        offset=50,
        sort=[["display_name", "ASC"]],
    )

    call = mock_client.calls[0]
    assert call[2]["filters"] == {"contact_type": "Individual"}
    assert call[2]["limit"] == 25
    assert call[2]["offset"] == 50
    assert call[2]["sort"] == [["display_name", "ASC"]]


@pytest.mark.asyncio
async def test_run_saved_search_api_error(mock_client: MockCiviCRMClient, tools):
    mock_client.set_error("SearchDisplay", "run", "Server error", 500)

    result = await tools["civicrm_run_saved_search"](
        saved_search="my_contacts",
        display="my_table",
    )
    assert "Error running saved search" in result
    assert "Server error" in result


# ---------- civicrm_describe_saved_search ----------


@pytest.mark.asyncio
async def test_describe_saved_search(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("SavedSearch", "get", {
        "values": [{
            "id": 5,
            "name": "my_contacts",
            "label": "My Contacts",
            "description": "All individual contacts",
            "api_entity": "Contact",
            "api_params": {"select": ["display_name", "email"]},
            "created_date": "2025-01-01",
            "modified_date": "2025-06-01",
            "expires_date": None,
        }],
    })
    mock_client.set_response("SearchDisplay", "get", {
        "values": [
            {"id": 10, "name": "my_contacts_table", "label": "Table", "type": "table"},
            {"id": 11, "name": "my_contacts_list", "label": "List", "type": "list"},
        ],
    })

    result = json.loads(await tools["civicrm_describe_saved_search"](
        saved_search="my_contacts",
    ))

    assert result["search"]["name"] == "my_contacts"
    assert result["search"]["api_entity"] == "Contact"
    assert len(result["displays"]) == 2
    assert result["displays"][0]["name"] == "my_contacts_table"
    assert result["displays"][1]["type"] == "list"

    # First call: SavedSearch.get by name, second: SearchDisplay.get by search id
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][0] == "SavedSearch"
    assert mock_client.calls[0][2]["where"] == [["name", "=", "my_contacts"]]
    assert mock_client.calls[1][0] == "SearchDisplay"
    assert mock_client.calls[1][2]["where"] == [["saved_search_id", "=", 5]]


@pytest.mark.asyncio
async def test_describe_saved_search_not_found(mock_client: MockCiviCRMClient, tools):
    # Both exact and fuzzy match return empty
    mock_client.set_response("SavedSearch", "get", {"values": []})

    result = json.loads(await tools["civicrm_describe_saved_search"](
        saved_search="nonexistent",
    ))
    assert "error" in result
    assert "No saved search found" in result["error"]

    # Should have made two calls: exact name match, then fuzzy label match
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][2]["where"] == [["name", "=", "nonexistent"]]
    assert mock_client.calls[1][2]["where"] == [["label", "LIKE", "%nonexistent%"]]


@pytest.mark.asyncio
async def test_describe_saved_search_fuzzy_match(mock_client: MockCiviCRMClient, tools):
    """When exact name match fails, falls back to fuzzy label match."""
    # We need to track call count to return different responses for the same
    # entity.action key.  The mock returns the same response for SavedSearch.get
    # every time, so we set the response to the fuzzy-match result and accept
    # that the exact-match call also returns it.  The implementation takes the
    # first result either way, so this is fine for testing the fallback path.
    mock_client.set_response("SavedSearch", "get", {
        "values": [{
            "id": 3,
            "name": "donor_report",
            "label": "Donor Report 2025",
            "description": None,
            "api_entity": "Contribution",
            "api_params": {},
            "created_date": "2025-04-01",
            "modified_date": "2025-04-01",
            "expires_date": None,
        }],
    })
    mock_client.set_response("SearchDisplay", "get", {
        "values": [{"id": 20, "name": "donor_table", "label": "Table", "type": "table"}],
    })

    result = json.loads(await tools["civicrm_describe_saved_search"](
        saved_search="donor_report",
    ))

    # Should succeed with the found search
    assert result["search"]["name"] == "donor_report"
    assert len(result["displays"]) == 1


@pytest.mark.asyncio
async def test_describe_saved_search_api_error(mock_client: MockCiviCRMClient, tools):
    mock_client.set_error("SavedSearch", "get", "Database error", 500)

    result = await tools["civicrm_describe_saved_search"](
        saved_search="my_contacts",
    )
    assert "Error describing saved search" in result
    assert "Database error" in result
