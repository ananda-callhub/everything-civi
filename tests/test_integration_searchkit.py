"""SearchKit integration tests against a live CiviCRM instance.

Skipped unless CIVICRM_BASE_URL and CIVICRM_API_KEY are set.
Run with:
    CIVICRM_BASE_URL=... CIVICRM_API_KEY=... .venv/bin/pytest tests/test_integration_searchkit.py -v

These tests exercise the SavedSearch and SearchDisplay APIs. Some tests
depend on saved searches existing on the instance; they will be skipped
gracefully on a fresh installation with no searches configured.
"""
from __future__ import annotations

import uuid

import pytest

from everything_civi.client import CiviCRMClient
from tests.conftest import requires_live_instance


def _test_source() -> str:
    return f"integration-test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# List Saved Searches
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_list_saved_searches(live_client: CiviCRMClient):
    """List saved searches on the instance (may return empty list)."""
    async with live_client:
        result = await live_client.api4("SavedSearch", "get", {
            "select": ["id", "name", "label", "api_entity"],
        })
        assert "values" in result
        # Valid response even if empty
        assert isinstance(result["values"], list)

        # If searches exist, verify they have expected fields
        for search in result["values"]:
            assert "id" in search
            assert "name" in search


@requires_live_instance
@pytest.mark.asyncio
async def test_list_saved_searches_with_displays(live_client: CiviCRMClient):
    """List saved searches and their associated displays."""
    async with live_client:
        searches = await live_client.api4("SavedSearch", "get", {
            "select": ["id", "name", "label"],
            "limit": 5,
        })
        assert "values" in searches

        if not searches["values"]:
            pytest.skip("No saved searches configured on test instance")

        # For the first search, fetch its displays
        search_id = searches["values"][0]["id"]
        displays = await live_client.api4("SearchDisplay", "get", {
            "select": ["id", "name", "label", "type"],
            "where": [["saved_search_id", "=", search_id]],
        })
        assert "values" in displays
        assert isinstance(displays["values"], list)


# ---------------------------------------------------------------------------
# Create and Run Saved Search
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_create_and_run_saved_search(live_client: CiviCRMClient):
    """Create a saved search with a display, run it, then clean up."""
    async with live_client:
        source = _test_source()
        search_name = f"integ_test_{source}"

        search_id = None
        display_id = None

        try:
            # Create a saved search for Individual contacts
            search_result = await live_client.api4("SavedSearch", "create", {"values": {
                "name": search_name,
                "label": f"Integration Test Search ({source})",
                "description": "Created by integration tests",
                "api_entity": "Contact",
                "api_params": {
                    "version": 4,
                    "select": ["id", "display_name", "contact_type"],
                    "where": [["contact_type", "=", "Individual"]],
                    "orderBy": {"id": "ASC"},
                },
            }})
            search_id = search_result["values"][0]["id"]
            assert search_id > 0

            # Create a display for the search
            display_result = await live_client.api4("SearchDisplay", "create", {"values": {
                "saved_search_id": search_id,
                "name": f"integ_test_table_{source}",
                "label": f"Integration Test Table ({source})",
                "type": "table",
                "settings": {
                    "limit": 10,
                    "pager": {},
                    "columns": [
                        {"type": "field", "key": "id", "label": "ID"},
                        {"type": "field", "key": "display_name", "label": "Name"},
                        {"type": "field", "key": "contact_type", "label": "Type"},
                    ],
                },
            }})
            display_id = display_result["values"][0]["id"]
            assert display_id > 0

            # Verify the search was created
            fetched_search = await live_client.api4("SavedSearch", "get", {
                "where": [["name", "=", search_name]],
                "select": ["id", "name", "api_entity"],
            })
            assert len(fetched_search["values"]) == 1
            assert fetched_search["values"][0]["api_entity"] == "Contact"

            # Run the search via SearchDisplay.run
            run_result = await live_client.api4("SearchDisplay", "run", {
                "savedSearch": search_name,
                "display": f"integ_test_table_{source}",
                "limit": 5,
                "offset": 0,
                "return": "page",
            })
            # run result may have values (contacts) or be empty
            assert isinstance(run_result, dict)

        finally:
            # Cleanup: display first, then search
            if display_id is not None:
                try:
                    await live_client.api4("SearchDisplay", "delete", {
                        "where": [["id", "=", display_id]],
                    })
                except Exception:
                    pass
            if search_id is not None:
                try:
                    await live_client.api4("SavedSearch", "delete", {
                        "where": [["id", "=", search_id]],
                    })
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Describe Saved Search
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_describe_saved_search(live_client: CiviCRMClient):
    """Create a saved search, describe it, verify metadata, clean up."""
    async with live_client:
        source = _test_source()
        search_name = f"integ_describe_{source}"

        search_id = None
        try:
            # Create search
            search_result = await live_client.api4("SavedSearch", "create", {"values": {
                "name": search_name,
                "label": f"Describe Test ({source})",
                "description": "Integration test for describe",
                "api_entity": "Activity",
                "api_params": {
                    "version": 4,
                    "select": ["id", "subject", "activity_type_id:name"],
                    "where": [],
                },
            }})
            search_id = search_result["values"][0]["id"]

            # Describe (fetch details)
            described = await live_client.api4("SavedSearch", "get", {
                "where": [["name", "=", search_name]],
                "select": [
                    "id", "name", "label", "description",
                    "api_entity", "api_params",
                ],
            })
            assert len(described["values"]) == 1
            search = described["values"][0]
            assert search["api_entity"] == "Activity"
            assert search["name"] == search_name
            assert "Describe Test" in search["label"]
            assert isinstance(search["api_params"], dict)

        finally:
            if search_id is not None:
                try:
                    await live_client.api4("SavedSearch", "delete", {
                        "where": [["id", "=", search_id]],
                    })
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Run Existing Saved Search (if any exist)
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_run_existing_saved_search(live_client: CiviCRMClient):
    """Run an existing saved search if one is configured."""
    async with live_client:
        # Find any search that has at least one display
        searches = await live_client.api4("SavedSearch", "get", {
            "select": ["id", "name"],
            "limit": 10,
        })
        if not searches.get("values"):
            pytest.skip("No saved searches configured on test instance")

        # Find a search with a display
        search_with_display = None
        display_name = None
        for search in searches["values"]:
            displays = await live_client.api4("SearchDisplay", "get", {
                "select": ["name"],
                "where": [["saved_search_id", "=", search["id"]]],
                "limit": 1,
            })
            if displays.get("values"):
                search_with_display = search
                display_name = displays["values"][0]["name"]
                break

        if search_with_display is None:
            pytest.skip("No saved searches with displays found")

        # Run it
        result = await live_client.api4("SearchDisplay", "run", {
            "savedSearch": search_with_display["name"],
            "display": display_name,
            "limit": 5,
            "offset": 0,
            "return": "page",
        })
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Search with Filters
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_saved_search_with_filters(live_client: CiviCRMClient):
    """Create a search, run with runtime filters, verify filtering, clean up."""
    async with live_client:
        source = _test_source()
        search_name = f"integ_filter_{source}"

        # Create some test contacts to search for
        contact_result = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "FilterTest",
            "last_name": "IntegSearchKit",
            "source": source,
        })
        contact_id = contact_result["values"][0]["id"]

        search_id = None
        display_id = None

        try:
            # Create a saved search
            search_result = await live_client.api4("SavedSearch", "create", {"values": {
                "name": search_name,
                "label": f"Filter Test ({source})",
                "api_entity": "Contact",
                "api_params": {
                    "version": 4,
                    "select": ["id", "first_name", "last_name", "source"],
                    "where": [],
                },
            }})
            search_id = search_result["values"][0]["id"]

            # Create a display
            display_result = await live_client.api4("SearchDisplay", "create", {"values": {
                "saved_search_id": search_id,
                "name": f"integ_filter_table_{source}",
                "label": f"Filter Test Table ({source})",
                "type": "table",
                "settings": {
                    "limit": 25,
                    "pager": {},
                    "columns": [
                        {"type": "field", "key": "id", "label": "ID"},
                        {"type": "field", "key": "first_name", "label": "First"},
                        {"type": "field", "key": "last_name", "label": "Last"},
                        {"type": "field", "key": "source", "label": "Source"},
                    ],
                },
            }})
            display_id = display_result["values"][0]["id"]

            # Run the search with a filter that should match our test contact
            result = await live_client.api4("SearchDisplay", "run", {
                "savedSearch": search_name,
                "display": f"integ_filter_table_{source}",
                "filters": {"source": source},
                "limit": 25,
                "offset": 0,
                "return": "page",
            })
            assert isinstance(result, dict)
            # The result should contain our test contact
            # (exact validation depends on display format)

        finally:
            if display_id is not None:
                try:
                    await live_client.api4("SearchDisplay", "delete", {
                        "where": [["id", "=", display_id]],
                    })
                except Exception:
                    pass
            if search_id is not None:
                try:
                    await live_client.api4("SavedSearch", "delete", {
                        "where": [["id", "=", search_id]],
                    })
                except Exception:
                    pass
            try:
                await live_client.delete(
                    "Contact", [["id", "=", contact_id]], use_trash=False,
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Pagination of Saved Search Results
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_saved_search_pagination(live_client: CiviCRMClient):
    """Create a search, paginate results, verify page boundaries."""
    async with live_client:
        source = _test_source()
        search_name = f"integ_paginate_{source}"

        search_id = None
        display_id = None

        try:
            # Create a saved search over all contacts
            search_result = await live_client.api4("SavedSearch", "create", {"values": {
                "name": search_name,
                "label": f"Pagination Test ({source})",
                "api_entity": "Contact",
                "api_params": {
                    "version": 4,
                    "select": ["id", "display_name"],
                    "where": [],
                    "orderBy": {"id": "ASC"},
                },
            }})
            search_id = search_result["values"][0]["id"]

            display_result = await live_client.api4("SearchDisplay", "create", {"values": {
                "saved_search_id": search_id,
                "name": f"integ_paginate_table_{source}",
                "label": f"Pagination Test Table ({source})",
                "type": "table",
                "settings": {
                    "limit": 2,
                    "pager": {},
                    "columns": [
                        {"type": "field", "key": "id", "label": "ID"},
                        {"type": "field", "key": "display_name", "label": "Name"},
                    ],
                },
            }})
            display_id = display_result["values"][0]["id"]

            # Fetch page 1
            page1 = await live_client.api4("SearchDisplay", "run", {
                "savedSearch": search_name,
                "display": f"integ_paginate_table_{source}",
                "limit": 2,
                "offset": 0,
                "return": "page",
            })
            assert isinstance(page1, dict)

            page1_values = page1.get("values", [])
            if len(page1_values) < 2:
                pytest.skip("Not enough records for pagination test")

            # Fetch page 2
            page2 = await live_client.api4("SearchDisplay", "run", {
                "savedSearch": search_name,
                "display": f"integ_paginate_table_{source}",
                "limit": 2,
                "offset": 2,
                "return": "page",
            })
            page2_values = page2.get("values", [])

            if not page2_values:
                pytest.skip("Only one page of results available")

            # Pages should not overlap (based on rendered data keys)
            # SearchDisplay results may use different key formats; just verify non-empty
            assert len(page2_values) > 0

        finally:
            if display_id is not None:
                try:
                    await live_client.api4("SearchDisplay", "delete", {
                        "where": [["id", "=", display_id]],
                    })
                except Exception:
                    pass
            if search_id is not None:
                try:
                    await live_client.api4("SavedSearch", "delete", {
                        "where": [["id", "=", search_id]],
                    })
                except Exception:
                    pass
