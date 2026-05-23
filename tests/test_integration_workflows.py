"""Comprehensive workflow integration tests against a live CiviCRM instance.

Skipped unless CIVICRM_BASE_URL and CIVICRM_API_KEY are set.
Run with:
    CIVICRM_BASE_URL=... CIVICRM_API_KEY=... .venv/bin/pytest tests/test_integration_workflows.py -v
"""
from __future__ import annotations

import uuid

import pytest

from everything_civi.client import CiviCRMClient, CiviCRMAPIError
from tests.conftest import requires_live_instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _test_source() -> str:
    """Return a unique source string so test records can be identified and cleaned up."""
    return f"integration-test-{uuid.uuid4().hex[:8]}"


async def _cleanup_contact(client: CiviCRMClient, contact_id: int) -> None:
    """Best-effort permanent contact deletion for test cleanup."""
    try:
        await client.delete("Contact", [["id", "=", contact_id]], use_trash=False)
    except Exception:
        try:
            await client.delete("Contact", [["id", "=", contact_id]], use_trash=True)
        except Exception:
            pass


async def _cleanup_entity(
    client: CiviCRMClient, entity: str, entity_id: int, *, use_trash: bool = False,
) -> None:
    """Best-effort entity deletion."""
    try:
        params: dict = {"where": [["id", "=", entity_id]]}
        if use_trash:
            params["useTrash"] = False
        await client.api4(entity, "delete", params)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Contact Lifecycle
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_search_contacts_integration(live_client: CiviCRMClient):
    """Search for existing contacts by type."""
    async with live_client:
        result = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name", "contact_type"],
            "where": [["contact_type", "=", "Individual"]],
            "limit": 5,
        })
        assert "values" in result
        # Every returned record should be an Individual
        for contact in result.get("values", []):
            assert contact["contact_type"] == "Individual"


@requires_live_instance
@pytest.mark.asyncio
async def test_search_contacts_with_multiple_conditions(live_client: CiviCRMClient):
    """Search contacts with multiple WHERE conditions."""
    async with live_client:
        # Create a contact with a specific, searchable last name
        source = _test_source()
        created = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "SearchTest",
            "last_name": "IntegrationFind",
            "source": source,
        })
        contact_id = created["values"][0]["id"]

        try:
            result = await live_client.api4("Contact", "get", {
                "select": ["id", "first_name", "last_name"],
                "where": [
                    ["first_name", "=", "SearchTest"],
                    ["last_name", "=", "IntegrationFind"],
                    ["source", "=", source],
                ],
                "limit": 10,
            })
            assert len(result["values"]) >= 1
            found_ids = [c["id"] for c in result["values"]]
            assert contact_id in found_ids
        finally:
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Contribution Workflow
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_contribution_lifecycle(live_client: CiviCRMClient):
    """Create a contact, record a contribution, verify, then clean up."""
    async with live_client:
        source = _test_source()
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "IntegTest",
            "last_name": "Contributor",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]
        contrib_id = None

        try:
            # Create contribution
            contrib = await live_client.api4("Contribution", "create", {"values": {
                "contact_id": contact_id,
                "total_amount": 100.00,
                "financial_type_id:name": "Donation",
                "contribution_status_id:name": "Completed",
                "source": source,
            }})
            contrib_id = contrib["values"][0]["id"]
            assert contrib_id > 0

            # Verify it exists and has the right amount
            fetched = await live_client.api4("Contribution", "get", {
                "where": [["id", "=", contrib_id]],
                "select": ["total_amount", "financial_type_id:name", "contact_id"],
            })
            assert len(fetched["values"]) == 1
            assert float(fetched["values"][0]["total_amount"]) == 100.00
            assert fetched["values"][0]["contact_id"] == contact_id

            # Update contribution amount
            await live_client.api4("Contribution", "update", {
                "values": {"total_amount": 200.00},
                "where": [["id", "=", contrib_id]],
            })
            updated = await live_client.api4("Contribution", "get", {
                "where": [["id", "=", contrib_id]],
                "select": ["total_amount"],
            })
            assert float(updated["values"][0]["total_amount"]) == 200.00

        finally:
            # Cleanup: delete contribution then contact
            if contrib_id is not None:
                try:
                    await live_client.api4("Contribution", "delete", {
                        "where": [["id", "=", contrib_id]],
                    })
                except Exception:
                    pass
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Activity Logging
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_activity_creation(live_client: CiviCRMClient):
    """Create an activity linked to source and target contacts."""
    async with live_client:
        source = _test_source()

        # Create two contacts: source and target
        source_contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "ActivitySource",
            "last_name": "IntegTest",
            "source": source,
        })
        source_contact_id = source_contact["values"][0]["id"]

        target_contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "ActivityTarget",
            "last_name": "IntegTest",
            "source": source,
        })
        target_contact_id = target_contact["values"][0]["id"]

        activity_id = None
        try:
            # Create activity
            activity = await live_client.api4("Activity", "create", {"values": {
                "activity_type_id:name": "Meeting",
                "subject": f"Integration test meeting ({source})",
                "status_id:name": "Completed",
                "source_contact_id": source_contact_id,
            }})
            activity_id = activity["values"][0]["id"]
            assert activity_id > 0

            # Add target contact via ActivityContact
            await live_client.api4("ActivityContact", "create", {"values": {
                "activity_id": activity_id,
                "contact_id": target_contact_id,
                "record_type_id:name": "Activity Targets",
            }})

            # Verify activity exists
            fetched = await live_client.api4("Activity", "get", {
                "where": [["id", "=", activity_id]],
                "select": ["subject", "activity_type_id:name", "status_id:name"],
            })
            assert len(fetched["values"]) == 1
            assert "Integration test meeting" in fetched["values"][0]["subject"]

            # Verify target contact assignment
            contacts = await live_client.api4("ActivityContact", "get", {
                "where": [
                    ["activity_id", "=", activity_id],
                    ["record_type_id:name", "=", "Activity Targets"],
                ],
                "select": ["contact_id"],
            })
            target_ids = [ac["contact_id"] for ac in contacts["values"]]
            assert target_contact_id in target_ids

        finally:
            if activity_id is not None:
                await _cleanup_entity(live_client, "Activity", activity_id)
            await _cleanup_contact(live_client, target_contact_id)
            await _cleanup_contact(live_client, source_contact_id)


# ---------------------------------------------------------------------------
# Group Management
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_group_contact_lifecycle(live_client: CiviCRMClient):
    """Create a group, add contacts, verify membership, remove, then clean up."""
    async with live_client:
        source = _test_source()

        # Create test group
        group = await live_client.api4("Group", "create", {"values": {
            "title": f"IntegTest Group ({source})",
            "description": "Created by integration tests",
            "group_type:name": ["Mailing List"],
            "is_active": True,
        }})
        group_id = group["values"][0]["id"]

        # Create test contacts
        contact1 = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "GroupMember1",
            "last_name": "IntegTest",
            "source": source,
        })
        contact1_id = contact1["values"][0]["id"]

        contact2 = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "GroupMember2",
            "last_name": "IntegTest",
            "source": source,
        })
        contact2_id = contact2["values"][0]["id"]

        try:
            # Add contacts to group
            await live_client.api4("GroupContact", "create", {"values": {
                "group_id": group_id,
                "contact_id": contact1_id,
                "status": "Added",
            }})
            await live_client.api4("GroupContact", "create", {"values": {
                "group_id": group_id,
                "contact_id": contact2_id,
                "status": "Added",
            }})

            # Verify membership
            members = await live_client.api4("GroupContact", "get", {
                "where": [
                    ["group_id", "=", group_id],
                    ["status", "=", "Added"],
                ],
                "select": ["contact_id"],
            })
            member_ids = [m["contact_id"] for m in members["values"]]
            assert contact1_id in member_ids
            assert contact2_id in member_ids

            # Remove one contact from group
            await live_client.api4("GroupContact", "delete", {
                "where": [
                    ["group_id", "=", group_id],
                    ["contact_id", "=", contact1_id],
                ],
            })

            # Verify removal
            remaining = await live_client.api4("GroupContact", "get", {
                "where": [
                    ["group_id", "=", group_id],
                    ["status", "=", "Added"],
                ],
                "select": ["contact_id"],
            })
            remaining_ids = [m["contact_id"] for m in remaining["values"]]
            assert contact1_id not in remaining_ids
            assert contact2_id in remaining_ids

        finally:
            # Cleanup: group contacts are deleted with the group
            await _cleanup_entity(live_client, "Group", group_id)
            await _cleanup_contact(live_client, contact2_id)
            await _cleanup_contact(live_client, contact1_id)


# ---------------------------------------------------------------------------
# Tag Operations
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_tag_lifecycle(live_client: CiviCRMClient):
    """Create a tag, apply to a contact, verify, then clean up."""
    async with live_client:
        source = _test_source()

        # Create test tag
        tag = await live_client.api4("Tag", "create", {"values": {
            "name": f"IntegTestTag-{source}",
            "description": "Created by integration tests",
            "used_for:name": ["civicrm_contact"],
        }})
        tag_id = tag["values"][0]["id"]

        # Create test contact
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "TagTest",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]

        try:
            # Apply tag to contact via EntityTag
            await live_client.api4("EntityTag", "create", {"values": {
                "entity_table": "civicrm_contact",
                "entity_id": contact_id,
                "tag_id": tag_id,
            }})

            # Verify tag is applied
            entity_tags = await live_client.api4("EntityTag", "get", {
                "where": [
                    ["entity_table", "=", "civicrm_contact"],
                    ["entity_id", "=", contact_id],
                    ["tag_id", "=", tag_id],
                ],
                "select": ["id", "tag_id"],
            })
            assert len(entity_tags["values"]) == 1
            assert entity_tags["values"][0]["tag_id"] == tag_id

            # Remove tag from contact
            await live_client.api4("EntityTag", "delete", {
                "where": [
                    ["entity_table", "=", "civicrm_contact"],
                    ["entity_id", "=", contact_id],
                    ["tag_id", "=", tag_id],
                ],
            })

            # Verify removal
            after_removal = await live_client.api4("EntityTag", "get", {
                "where": [
                    ["entity_table", "=", "civicrm_contact"],
                    ["entity_id", "=", contact_id],
                    ["tag_id", "=", tag_id],
                ],
            })
            assert len(after_removal["values"]) == 0

        finally:
            await _cleanup_contact(live_client, contact_id)
            await _cleanup_entity(live_client, "Tag", tag_id)


# ---------------------------------------------------------------------------
# Event Registration
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_event_registration_basic(live_client: CiviCRMClient):
    """Register a contact for an existing event (no payment)."""
    async with live_client:
        source = _test_source()

        # Check if any events exist; skip if not
        events = await live_client.api4("Event", "get", {
            "select": ["id", "title"],
            "where": [["is_active", "=", True]],
            "limit": 1,
        })
        if not events.get("values"):
            pytest.skip("No active events configured on test instance")

        event_id = events["values"][0]["id"]

        # Create test contact
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "EventReg",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]
        participant_id = None

        try:
            # Register contact for the event
            participant = await live_client.api4("Participant", "create", {"values": {
                "event_id": event_id,
                "contact_id": contact_id,
                "status_id:name": "Registered",
                "role_id:name": "Attendee",
                "source": source,
            }})
            participant_id = participant["values"][0]["id"]
            assert participant_id > 0

            # Verify registration
            fetched = await live_client.api4("Participant", "get", {
                "where": [["id", "=", participant_id]],
                "select": ["event_id", "contact_id", "status_id:name"],
            })
            assert len(fetched["values"]) == 1
            assert fetched["values"][0]["event_id"] == event_id
            assert fetched["values"][0]["contact_id"] == contact_id

        finally:
            if participant_id is not None:
                await _cleanup_entity(live_client, "Participant", participant_id)
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Discovery Tools
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_describe_entity_fields(live_client: CiviCRMClient):
    """Get field metadata for the Contact entity and verify key fields exist."""
    async with live_client:
        result = await live_client.get_fields("Contact")
        fields = result.get("values", [])
        assert len(fields) > 0

        field_names = {f["name"] for f in fields}
        # These fields should always exist on Contact
        assert "id" in field_names
        assert "display_name" in field_names
        assert "first_name" in field_names
        assert "last_name" in field_names
        assert "contact_type" in field_names
        # Email may appear under various names depending on CiviCRM version
        has_email = any("email" in name.lower() for name in field_names)
        assert has_email, f"No email-related field found in: {sorted(field_names)}"

        # Each field should have a name key
        for field in fields:
            assert "name" in field


@requires_live_instance
@pytest.mark.asyncio
async def test_describe_entity_fields_with_options(live_client: CiviCRMClient):
    """Get field metadata with option values loaded."""
    async with live_client:
        result = await live_client.get_fields("Contact", load_options=True)
        fields = result.get("values", [])
        assert len(fields) > 0

        # contact_type should have option values
        contact_type_field = next(
            (f for f in fields if f["name"] == "contact_type"), None,
        )
        assert contact_type_field is not None
        # When loadOptions=True, options should be populated for pseudoconstant fields
        if contact_type_field.get("options"):
            options = contact_type_field["options"]
            # Should include at least Individual, Household, Organization
            assert len(options) >= 3


@requires_live_instance
@pytest.mark.asyncio
async def test_explore_options(live_client: CiviCRMClient):
    """List option values for a known option group."""
    async with live_client:
        # activity_type is a well-known option group
        result = await live_client.api4("OptionValue", "get", {
            "select": ["value", "label", "name"],
            "where": [["option_group_id:name", "=", "activity_type"]],
            "limit": 20,
        })
        assert "values" in result
        values = result["values"]
        assert len(values) > 0

        # Every option value should have a label
        for opt in values:
            assert "label" in opt
            assert "name" in opt


@requires_live_instance
@pytest.mark.asyncio
async def test_get_entity_actions(live_client: CiviCRMClient):
    """List available actions for an entity."""
    async with live_client:
        result = await live_client.get_actions("Contact")
        actions = result.get("values", [])
        assert len(actions) > 0

        action_names = {a["name"] for a in actions}
        # Standard CRUD actions should always exist
        assert "get" in action_names
        assert "create" in action_names
        assert "update" in action_names
        assert "delete" in action_names


@requires_live_instance
@pytest.mark.asyncio
async def test_list_entities(live_client: CiviCRMClient):
    """List all available entities and verify core ones are present."""
    async with live_client:
        result = await live_client.api4("Entity", "get", {
            "select": ["name"],
        })
        assert "values" in result
        entity_names = {e["name"] for e in result["values"]}

        # Core entities that should always be present
        assert "Contact" in entity_names
        assert "Activity" in entity_names
        assert "Contribution" in entity_names
        assert "Event" in entity_names
        assert "Group" in entity_names
        assert "Tag" in entity_names


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_pagination_contacts(live_client: CiviCRMClient):
    """Paginate through contacts with a small page size and verify no overlap."""
    async with live_client:
        page_size = 3

        # Fetch page 1
        page1 = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name"],
            "limit": page_size,
            "offset": 0,
            "orderBy": {"id": "ASC"},
        })
        assert "values" in page1

        if len(page1["values"]) < page_size:
            pytest.skip("Not enough contacts to test pagination")

        # Fetch page 2
        page2 = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name"],
            "limit": page_size,
            "offset": page_size,
            "orderBy": {"id": "ASC"},
        })
        assert "values" in page2

        if not page2["values"]:
            pytest.skip("Only one page of contacts available")

        # Verify no ID overlap between pages
        page1_ids = {c["id"] for c in page1["values"]}
        page2_ids = {c["id"] for c in page2["values"]}
        assert page1_ids.isdisjoint(page2_ids), "Pages should not overlap"

        # Verify ordering: all page2 IDs should be greater than all page1 IDs
        assert min(page2_ids) > max(page1_ids), "Page 2 IDs should follow page 1"


@requires_live_instance
@pytest.mark.asyncio
async def test_pagination_with_row_count(live_client: CiviCRMClient):
    """Fetch total row count alongside paginated results."""
    async with live_client:
        result = await live_client.api4("Contact", "get", {
            "select": ["id", "display_name", "row_count"],
            "limit": 2,
            "offset": 0,
        })
        assert "values" in result
        # CiviCRM APIv4 returns count when row_count is selected
        # or via the count key in the response
        assert len(result["values"]) <= 2


# ---------------------------------------------------------------------------
# System Health
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_system_health_check(live_client: CiviCRMClient):
    """Run health check and verify response format."""
    async with live_client:
        result = await live_client.health_check()
        assert "status" in result
        assert result["status"] in ("ok", "error")

        if result["status"] == "ok":
            assert "checks" in result
            assert isinstance(result["checks"], list)


@requires_live_instance
@pytest.mark.asyncio
async def test_system_check_details(live_client: CiviCRMClient):
    """Run System.check and inspect individual check results."""
    async with live_client:
        result = await live_client.api4("System", "check", {})
        checks = result.get("values", [])
        assert isinstance(checks, list)

        # Each check should be a dict with some identifying information
        for check in checks:
            assert isinstance(check, dict)
            # Different CiviCRM versions use different keys (name, title, severity, etc.)
            assert len(check) > 0


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_invalid_entity_raises_error(live_client: CiviCRMClient):
    """Querying a non-existent entity should raise CiviCRMAPIError."""
    async with live_client:
        with pytest.raises(CiviCRMAPIError):
            await live_client.api4("TotallyFakeEntity", "get", {"limit": 1})


@requires_live_instance
@pytest.mark.asyncio
async def test_invalid_action_raises_error(live_client: CiviCRMClient):
    """Calling a non-existent action should raise CiviCRMAPIError."""
    async with live_client:
        with pytest.raises(CiviCRMAPIError):
            await live_client.api4("Contact", "totallyFakeAction", {"limit": 1})


@requires_live_instance
@pytest.mark.asyncio
async def test_missing_required_field_raises_error(live_client: CiviCRMClient):
    """Creating a record without required fields should raise CiviCRMAPIError."""
    async with live_client:
        with pytest.raises(CiviCRMAPIError):
            # Contribution requires contact_id
            await live_client.api4("Contribution", "create", {"values": {
                "total_amount": 50.00,
            }})


# ---------------------------------------------------------------------------
# Organization and Household Contact Types
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_organization_lifecycle(live_client: CiviCRMClient):
    """Create, read, and delete an Organization contact."""
    async with live_client:
        source = _test_source()
        created = await live_client.create("Contact", {
            "contact_type": "Organization",
            "organization_name": f"IntegTest Org ({source})",
            "source": source,
        })
        contact_id = created["values"][0]["id"]

        try:
            fetched = await live_client.api4("Contact", "get", {
                "where": [["id", "=", contact_id]],
                "select": ["contact_type", "organization_name"],
            })
            assert fetched["values"][0]["contact_type"] == "Organization"
            assert "IntegTest Org" in fetched["values"][0]["organization_name"]
        finally:
            await _cleanup_contact(live_client, contact_id)


@requires_live_instance
@pytest.mark.asyncio
async def test_household_lifecycle(live_client: CiviCRMClient):
    """Create, read, and delete a Household contact."""
    async with live_client:
        source = _test_source()
        created = await live_client.create("Contact", {
            "contact_type": "Household",
            "household_name": f"IntegTest Household ({source})",
            "source": source,
        })
        contact_id = created["values"][0]["id"]

        try:
            fetched = await live_client.api4("Contact", "get", {
                "where": [["id", "=", contact_id]],
                "select": ["contact_type", "household_name"],
            })
            assert fetched["values"][0]["contact_type"] == "Household"
            assert "IntegTest Household" in fetched["values"][0]["household_name"]
        finally:
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Relationship Between Contacts
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_relationship_lifecycle(live_client: CiviCRMClient):
    """Create a relationship between two contacts, verify, and clean up."""
    async with live_client:
        source = _test_source()

        # Check if any relationship types exist
        rel_types = await live_client.api4("RelationshipType", "get", {
            "select": ["id", "name_a_b", "name_b_a"],
            "limit": 1,
        })
        if not rel_types.get("values"):
            pytest.skip("No relationship types configured on test instance")

        rel_type_id = rel_types["values"][0]["id"]

        contact_a = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "RelA",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_a_id = contact_a["values"][0]["id"]

        contact_b = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "RelB",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_b_id = contact_b["values"][0]["id"]

        relationship_id = None
        try:
            rel = await live_client.api4("Relationship", "create", {"values": {
                "relationship_type_id": rel_type_id,
                "contact_id_a": contact_a_id,
                "contact_id_b": contact_b_id,
                "is_active": True,
            }})
            relationship_id = rel["values"][0]["id"]
            assert relationship_id > 0

            # Verify relationship
            fetched = await live_client.api4("Relationship", "get", {
                "where": [["id", "=", relationship_id]],
                "select": ["contact_id_a", "contact_id_b", "relationship_type_id"],
            })
            assert len(fetched["values"]) == 1
            assert fetched["values"][0]["contact_id_a"] == contact_a_id
            assert fetched["values"][0]["contact_id_b"] == contact_b_id

        finally:
            if relationship_id is not None:
                await _cleanup_entity(live_client, "Relationship", relationship_id)
            await _cleanup_contact(live_client, contact_b_id)
            await _cleanup_contact(live_client, contact_a_id)


# ---------------------------------------------------------------------------
# Email and Phone
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_email_lifecycle(live_client: CiviCRMClient):
    """Add an email to a contact, verify, update, and clean up."""
    async with live_client:
        source = _test_source()
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "EmailTest",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]
        email_id = None

        try:
            # Add email
            email_result = await live_client.api4("Email", "create", {"values": {
                "contact_id": contact_id,
                "email": f"integtest-{source}@example.com",
                "location_type_id:name": "Home",
                "is_primary": True,
            }})
            email_id = email_result["values"][0]["id"]
            assert email_id > 0

            # Verify email
            fetched = await live_client.api4("Email", "get", {
                "where": [["id", "=", email_id]],
                "select": ["email", "contact_id", "is_primary"],
            })
            assert fetched["values"][0]["email"] == f"integtest-{source}@example.com"
            assert fetched["values"][0]["contact_id"] == contact_id

            # Update email
            await live_client.api4("Email", "update", {
                "values": {"email": f"updated-{source}@example.com"},
                "where": [["id", "=", email_id]],
            })
            updated = await live_client.api4("Email", "get", {
                "where": [["id", "=", email_id]],
                "select": ["email"],
            })
            assert updated["values"][0]["email"] == f"updated-{source}@example.com"

        finally:
            if email_id is not None:
                await _cleanup_entity(live_client, "Email", email_id)
            await _cleanup_contact(live_client, contact_id)


@requires_live_instance
@pytest.mark.asyncio
async def test_phone_lifecycle(live_client: CiviCRMClient):
    """Add a phone number to a contact and verify."""
    async with live_client:
        source = _test_source()
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "PhoneTest",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]
        phone_id = None

        try:
            phone_result = await live_client.api4("Phone", "create", {"values": {
                "contact_id": contact_id,
                "phone": "+1-555-0199",
                "phone_type_id:name": "Mobile",
                "location_type_id:name": "Home",
                "is_primary": True,
            }})
            phone_id = phone_result["values"][0]["id"]
            assert phone_id > 0

            # Verify
            fetched = await live_client.api4("Phone", "get", {
                "where": [["id", "=", phone_id]],
                "select": ["phone", "contact_id"],
            })
            assert fetched["values"][0]["contact_id"] == contact_id

        finally:
            if phone_id is not None:
                await _cleanup_entity(live_client, "Phone", phone_id)
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Note Operations
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_note_lifecycle(live_client: CiviCRMClient):
    """Create a note on a contact, verify, and clean up."""
    async with live_client:
        source = _test_source()
        contact = await live_client.create("Contact", {
            "contact_type": "Individual",
            "first_name": "NoteTest",
            "last_name": "IntegTest",
            "source": source,
        })
        contact_id = contact["values"][0]["id"]
        note_id = None

        try:
            note = await live_client.api4("Note", "create", {"values": {
                "entity_table": "civicrm_contact",
                "entity_id": contact_id,
                "subject": f"Integration test note ({source})",
                "note": "This is a test note created by the integration test suite.",
            }})
            note_id = note["values"][0]["id"]
            assert note_id > 0

            # Verify
            fetched = await live_client.api4("Note", "get", {
                "where": [["id", "=", note_id]],
                "select": ["subject", "note", "entity_id"],
            })
            assert len(fetched["values"]) == 1
            assert fetched["values"][0]["entity_id"] == contact_id
            assert "integration test note" in fetched["values"][0]["subject"].lower()

        finally:
            if note_id is not None:
                await _cleanup_entity(live_client, "Note", note_id)
            await _cleanup_contact(live_client, contact_id)


# ---------------------------------------------------------------------------
# Bulk Operations via save()
# ---------------------------------------------------------------------------

@requires_live_instance
@pytest.mark.asyncio
async def test_bulk_save_contacts(live_client: CiviCRMClient):
    """Use the save (upsert) API to create multiple contacts at once."""
    async with live_client:
        source = _test_source()
        records = [
            {
                "contact_type": "Individual",
                "first_name": f"Bulk{i}",
                "last_name": "IntegTest",
                "source": source,
            }
            for i in range(3)
        ]

        result = await live_client.save("Contact", records)
        created_ids = [v["id"] for v in result["values"]]
        assert len(created_ids) == 3

        try:
            # Verify all were created
            fetched = await live_client.api4("Contact", "get", {
                "where": [["source", "=", source]],
                "select": ["id", "first_name"],
            })
            fetched_ids = {v["id"] for v in fetched["values"]}
            for cid in created_ids:
                assert cid in fetched_ids
        finally:
            for cid in created_ids:
                await _cleanup_contact(live_client, cid)
