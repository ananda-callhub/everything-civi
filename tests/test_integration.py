"""Integration tests that run against a live CiviCRM instance.

Skipped unless CIVICRM_BASE_URL and CIVICRM_API_KEY are set.
Run with: CIVICRM_BASE_URL=... CIVICRM_API_KEY=... .venv/bin/pytest tests/test_integration.py -v
"""
from __future__ import annotations

import pytest

from everything_civi.client import CiviCRMClient, CiviCRMAPIError
from tests.conftest import requires_live_instance


@requires_live_instance
@pytest.mark.asyncio
async def test_list_entities(live_client: CiviCRMClient):
    async with live_client:
        result = await live_client.api4("Entity", "get", {
            "select": ["name", "title"],
            "limit": 5,
        })
        assert "values" in result
        assert len(result["values"]) > 0
        assert "name" in result["values"][0]


@requires_live_instance
@pytest.mark.asyncio
async def test_get_contacts(live_client: CiviCRMClient):
    async with live_client:
        result = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name"],
            "limit": 3,
        })
        assert "values" in result
        assert len(result["values"]) > 0


@requires_live_instance
@pytest.mark.asyncio
async def test_get_fields(live_client: CiviCRMClient):
    async with live_client:
        result = await live_client.get_fields("Contact")
        fields = result.get("values", [])
        assert len(fields) > 0
        field_names = [f["name"] for f in fields]
        assert "id" in field_names
        assert "display_name" in field_names


@requires_live_instance
@pytest.mark.asyncio
async def test_contact_crud_lifecycle(live_client: CiviCRMClient):
    """Create → read → update → delete a contact."""
    async with live_client:
        created = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "MCP",
            "last_name": "TestContact",
            "source": "integration-test",
        })
        contact_id = created["values"][0]["id"]

        try:
            # Read back and verify using display_name (reliable across versions)
            fetched = await live_client.api4("Contact", "get", {
                "where": [["id", "=", contact_id]],
                "select": ["id", "display_name"],
            })
            assert "MCP" in fetched["values"][0]["display_name"]

            # Update and verify
            await live_client.update(
                "Contact",
                {"first_name": "MCPUpdated"},
                [["id", "=", contact_id]],
            )
            updated = await live_client.api4("Contact", "get", {
                "where": [["id", "=", contact_id]],
                "select": ["display_name"],
            })
            assert "MCPUpdated" in updated["values"][0]["display_name"]

        finally:
            # Soft delete first (always works), then try permanent delete
            try:
                await live_client.delete("Contact", [["id", "=", contact_id]], use_trash=False)
            except CiviCRMAPIError:
                # Permanent delete may require special permissions; soft delete as fallback
                await live_client.delete("Contact", [["id", "=", contact_id]], use_trash=True)


@requires_live_instance
@pytest.mark.asyncio
async def test_invalid_entity_returns_error(live_client: CiviCRMClient):
    async with live_client:
        with pytest.raises(CiviCRMAPIError):
            await live_client.api4("NonExistentEntity", "get", {"limit": 1})


@requires_live_instance
@pytest.mark.asyncio
async def test_pseudoconstant_query(live_client: CiviCRMClient):
    async with live_client:
        result = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name", "contact_type"],
            "where": [["contact_type", "=", "Individual"]],
            "limit": 1,
        })
        if result.get("values"):
            assert result["values"][0]["contact_type"] == "Individual"
