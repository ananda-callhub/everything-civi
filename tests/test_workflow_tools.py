"""Unit tests for workflow tools using MockCiviCRMClient."""
from __future__ import annotations

import json

import pytest

from mcp.server.fastmcp import FastMCP

from everything_civi.workflow_tools import register_workflow_tools
from tests.conftest import MockCiviCRMClient


@pytest.fixture
def tools(mock_client: MockCiviCRMClient) -> dict:
    """Register workflow tools and return them as a name→function dict."""
    mcp = FastMCP("test")
    register_workflow_tools(mcp, mock_client)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


@pytest.mark.asyncio
async def test_search_contacts(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Contact", "get", {
        "values": [
            {"id": 1, "display_name": "Alice Smith", "contact_type": "Individual",
             "first_name": "Alice", "last_name": "Smith", "e.email": "alice@example.com", "p.phone": None},
        ],
    })

    result = json.loads(await tools["civicrm_search_contacts"](query="Alice"))
    assert len(result) == 1
    assert result[0]["display_name"] == "Alice Smith"

    call = mock_client.calls[0]
    assert call[0] == "Contact"
    assert call[1] == "get"
    assert any("LIKE" in str(c) for c in call[2]["where"])


@pytest.mark.asyncio
async def test_search_contacts_with_type_filter(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Contact", "get", {"values": []})

    await tools["civicrm_search_contacts"](query="Acme", contact_type="Organization")
    params = mock_client.calls[0][2]
    assert ["contact_type", "=", "Organization"] in params["where"]


@pytest.mark.asyncio
async def test_record_contribution(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Contribution", "create", {
        "values": [{"id": 100, "total_amount": 50.0}],
    })

    result = json.loads(await tools["civicrm_record_contribution"](
        contact_id=1, total_amount=50.0, financial_type="Donation",
    ))
    assert result["values"][0]["id"] == 100

    call = mock_client.calls[0]
    assert call[0] == "Contribution"
    assert call[2]["values"]["financial_type_id:name"] == "Donation"


@pytest.mark.asyncio
async def test_record_contribution_with_note(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Contribution", "create", {
        "values": [{"id": 101}],
    })
    mock_client.set_response("Note", "create", {
        "values": [{"id": 1}],
    })

    await tools["civicrm_record_contribution"](
        contact_id=1, total_amount=25.0, note="Thank you gift",
    )
    assert len(mock_client.calls) == 2
    note_call = mock_client.calls[1]
    assert note_call[0] == "Note"
    assert note_call[2]["values"]["note"] == "Thank you gift"
    assert note_call[2]["values"]["entity_id"] == 101


@pytest.mark.asyncio
async def test_manage_membership_create(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Membership", "create", {
        "values": [{"id": 10, "status_id": 1}],
    })

    result = json.loads(await tools["civicrm_manage_membership"](
        contact_id=1, membership_type="General", action="create",
    ))
    assert result["values"][0]["id"] == 10

    call = mock_client.calls[0]
    assert call[2]["values"]["membership_type_id:name"] == "General"
    assert call[2]["values"]["status_id:name"] == "New"


@pytest.mark.asyncio
async def test_manage_membership_cancel(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Membership", "get", {
        "values": [{"id": 10}],
    })
    mock_client.set_response("Membership", "update", {
        "values": [{"id": 10, "status_id:name": "Cancelled"}],
    })

    await tools["civicrm_manage_membership"](
        contact_id=1, membership_type="General", action="cancel",
    )
    assert mock_client.calls[0][1] == "get"
    assert mock_client.calls[1][1] == "update"
    assert mock_client.calls[1][2]["values"]["status_id:name"] == "Cancelled"


@pytest.mark.asyncio
async def test_manage_membership_cancel_not_found(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Membership", "get", {"values": []})

    result = json.loads(await tools["civicrm_manage_membership"](
        contact_id=999, membership_type="General", action="cancel",
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_manage_membership_invalid_action(mock_client: MockCiviCRMClient, tools):
    result = json.loads(await tools["civicrm_manage_membership"](
        contact_id=1, membership_type="General", action="upgrade",
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_register_for_event_basic(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Participant", "create", {
        "values": [{"id": 50}],
    })

    result = json.loads(await tools["civicrm_register_for_event"](
        contact_id=1, event_id=5,
    ))
    assert result["participant"][0]["id"] == 50
    assert len(mock_client.calls) == 1


@pytest.mark.asyncio
async def test_register_for_event_with_payment(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Participant", "create", {
        "values": [{"id": 50}],
    })
    mock_client.set_response("Event", "get", {
        "values": [{"title": "Gala", "financial_type_id:name": "Event Fee"}],
    })
    mock_client.set_response("Contribution", "create", {
        "values": [{"id": 200}],
    })
    mock_client.set_response("ParticipantPayment", "create", {
        "values": [{"id": 1}],
    })

    result = json.loads(await tools["civicrm_register_for_event"](
        contact_id=1, event_id=5, record_contribution=True, contribution_amount=100.0,
    ))
    assert "participant" in result
    assert "contribution" in result
    assert len(mock_client.calls) == 4


@pytest.mark.asyncio
async def test_log_activity(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Activity", "create", {
        "values": [{"id": 30}],
    })

    result = json.loads(await tools["civicrm_log_activity"](
        activity_type="Meeting", subject="Weekly sync", source_contact_id=2,
        target_contact_ids=[1, 3],
    ))
    assert result["values"][0]["id"] == 30

    call = mock_client.calls[0]
    assert call[2]["values"]["target_contact_id"] == [1, 3]


@pytest.mark.asyncio
async def test_manage_group_contacts_add(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Group", "get", {
        "values": [{"id": 7, "title": "Volunteers"}],
    })
    mock_client.set_response("GroupContact", "save", {
        "values": [{"id": 1}, {"id": 2}],
    })

    await tools["civicrm_manage_group_contacts"](
        contact_ids=[1, 2], group_title="Volunteers", action="add",
    )
    assert mock_client.calls[0][0] == "Group"
    assert mock_client.calls[1][0] == "GroupContact"
    assert mock_client.calls[1][1] == "save"


@pytest.mark.asyncio
async def test_manage_group_contacts_no_group(mock_client: MockCiviCRMClient, tools):
    result = json.loads(await tools["civicrm_manage_group_contacts"](
        contact_ids=[1], action="add",
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_manage_relationship_create(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("RelationshipType", "get", {
        "values": [{"id": 4, "name_a_b": "Employee of", "name_b_a": "Employer of"}],
    })
    mock_client.set_response("Relationship", "create", {
        "values": [{"id": 20}],
    })

    result = json.loads(await tools["civicrm_manage_relationship"](
        contact_id_a=10, contact_id_b=20, relationship_type="Employee of",
    ))
    assert result["values"][0]["id"] == 20


@pytest.mark.asyncio
async def test_manage_relationship_type_not_found(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("RelationshipType", "get", {"values": []})

    result = json.loads(await tools["civicrm_manage_relationship"](
        contact_id_a=10, contact_id_b=20, relationship_type="Nonexistent",
    ))
    assert "error" in result


@pytest.mark.asyncio
async def test_open_case(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Case", "create", {
        "values": [{"id": 5}],
    })

    result = json.loads(await tools["civicrm_open_case"](
        contact_id=1, case_type="Housing Support", subject="Needs housing",
    ))
    assert result["values"][0]["id"] == 5
    call = mock_client.calls[0]
    assert call[2]["values"]["case_type_id:name"] == "Housing Support"


@pytest.mark.asyncio
async def test_add_tags_creates_missing(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Tag", "get", {"values": []})
    mock_client.set_response("Tag", "create", {"values": [{"id": 99}]})
    mock_client.set_response("EntityTag", "save", {"values": [{"id": 1}]})

    await tools["civicrm_add_tags"](entity_id=1, tag_names=["VIP"])

    tag_create = [c for c in mock_client.calls if c[0] == "Tag" and c[1] == "create"]
    assert len(tag_create) == 1
    assert tag_create[0][2]["values"]["name"] == "VIP"

    entity_tag = [c for c in mock_client.calls if c[0] == "EntityTag"]
    assert len(entity_tag) == 1


@pytest.mark.asyncio
async def test_add_tags_reuses_existing(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Tag", "get", {"values": [{"id": 42, "name": "Donor"}]})
    mock_client.set_response("EntityTag", "save", {"values": [{"id": 1}]})

    await tools["civicrm_add_tags"](entity_id=1, tag_names=["Donor"])

    tag_creates = [c for c in mock_client.calls if c[0] == "Tag" and c[1] == "create"]
    assert len(tag_creates) == 0


@pytest.mark.asyncio
async def test_manage_membership_renew(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("Membership", "get", {
        "values": [{"id": 10, "end_date": "2025-12-31"}],
    })
    mock_client.set_response("Membership", "update", {
        "values": [{"id": 10, "status_id:name": "Current"}],
    })
    json.loads(await tools["civicrm_manage_membership"](
        contact_id=1, membership_type="General", action="renew", end_date="2026-12-31",
    ))
    assert mock_client.calls[0][1] == "get"
    assert mock_client.calls[1][1] == "update"
    assert mock_client.calls[1][2]["values"]["status_id:name"] == "Current"
    assert mock_client.calls[1][2]["values"]["end_date"] == "2026-12-31"


@pytest.mark.asyncio
async def test_manage_group_contacts_remove(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("GroupContact", "save", {
        "values": [{"id": 1}],
    })
    json.loads(await tools["civicrm_manage_group_contacts"](
        contact_ids=[1, 2], group_id=7, action="remove",
    ))
    call = mock_client.calls[0]
    assert call[0] == "GroupContact"
    assert call[1] == "save"
    # Verify status is "Removed" (not delete)
    for record in call[2]["records"]:
        assert record["status"] == "Removed"


@pytest.mark.asyncio
async def test_manage_relationship_disable(mock_client: MockCiviCRMClient, tools):
    mock_client.set_response("RelationshipType", "get", {
        "values": [{"id": 4, "name_a_b": "Employee of", "name_b_a": "Employer of"}],
    })
    mock_client.set_response("Relationship", "get", {
        "values": [{"id": 20, "is_active": True}],
    })
    mock_client.set_response("Relationship", "update", {
        "values": [{"id": 20, "is_active": False}],
    })
    json.loads(await tools["civicrm_manage_relationship"](
        contact_id_a=10, contact_id_b=20, relationship_type="Employee of", action="disable",
    ))
    # Should look up type, then find existing, then update
    assert mock_client.calls[0][:3] == ("RelationshipType", "get", mock_client.calls[0][2])
    assert mock_client.calls[1][0] == "Relationship"
    assert mock_client.calls[1][1] == "get"
    assert mock_client.calls[2][0] == "Relationship"
    assert mock_client.calls[2][1] == "update"
    assert mock_client.calls[2][2]["values"]["is_active"] is False


@pytest.mark.asyncio
async def test_search_contacts_api_error(mock_client: MockCiviCRMClient, tools):
    mock_client.set_error("Contact", "get", "Permission denied", 403)
    result = await tools["civicrm_search_contacts"](query="test")
    assert "Error searching contacts" in result
    assert "Permission denied" in result


@pytest.mark.asyncio
async def test_register_event_missing_contribution_amount(mock_client: MockCiviCRMClient, tools):
    result = json.loads(await tools["civicrm_register_for_event"](
        contact_id=1, event_id=5, record_contribution=True, contribution_amount=None,
    ))
    assert "error" in result
    # Validation should happen BEFORE any API calls — no participant created
    assert len(mock_client.calls) == 0


@pytest.mark.asyncio
async def test_register_for_event_contribution_failure_rolls_back(
    mock_client: MockCiviCRMClient, tools,
):
    """When Contribution.create fails, the participant should be cleaned up."""
    mock_client.set_response("Event", "get", {
        "values": [{"title": "Gala", "financial_type_id:name": "Event Fee"}],
    })
    mock_client.set_response("Participant", "create", {
        "values": [{"id": 50}],
    })
    mock_client.set_error("Contribution", "create", "Insufficient funds", 400)
    # Participant.delete for cleanup — use default empty response
    mock_client.set_response("Participant", "delete", {"values": []})

    result = await tools["civicrm_register_for_event"](
        contact_id=1, event_id=5, record_contribution=True, contribution_amount=100.0,
    )

    # Should report rollback error
    assert "Error registering for event" in result
    assert "rolled back" in result

    # Verify cleanup: Participant.delete was called with the orphaned participant ID
    delete_calls = [
        c for c in mock_client.calls
        if c[0] == "Participant" and c[1] == "delete"
    ]
    assert len(delete_calls) == 1
    assert delete_calls[0][2]["where"] == [["id", "=", 50]]


@pytest.mark.asyncio
async def test_register_for_event_payment_link_failure_rolls_back(
    mock_client: MockCiviCRMClient, tools,
):
    """When ParticipantPayment.create fails, both participant and contribution are cleaned up."""
    mock_client.set_response("Event", "get", {
        "values": [{"title": "Gala", "financial_type_id:name": "Event Fee"}],
    })
    mock_client.set_response("Participant", "create", {
        "values": [{"id": 50}],
    })
    mock_client.set_response("Contribution", "create", {
        "values": [{"id": 200}],
    })
    mock_client.set_error("ParticipantPayment", "create", "Link failed", 500)
    # Cleanup responses
    mock_client.set_response("Contribution", "delete", {"values": []})
    mock_client.set_response("Participant", "delete", {"values": []})

    result = await tools["civicrm_register_for_event"](
        contact_id=1, event_id=5, record_contribution=True, contribution_amount=100.0,
    )

    # Should report rollback error
    assert "Error registering for event" in result
    assert "rolled back" in result

    # Verify cleanup: both Contribution.delete and Participant.delete were called
    contrib_delete_calls = [
        c for c in mock_client.calls
        if c[0] == "Contribution" and c[1] == "delete"
    ]
    assert len(contrib_delete_calls) == 1
    assert contrib_delete_calls[0][2]["where"] == [["id", "=", 200]]

    participant_delete_calls = [
        c for c in mock_client.calls
        if c[0] == "Participant" and c[1] == "delete"
    ]
    assert len(participant_delete_calls) == 1
    assert participant_delete_calls[0][2]["where"] == [["id", "=", 50]]


@pytest.mark.asyncio
async def test_record_contribution_note_failure_returns_warning(
    mock_client: MockCiviCRMClient, tools,
):
    """When Note.create fails, contribution is kept but a warning is included."""
    mock_client.set_response("Contribution", "create", {
        "values": [{"id": 101}],
    })
    mock_client.set_error("Note", "create", "Note storage error", 500)

    result = json.loads(await tools["civicrm_record_contribution"](
        contact_id=1, total_amount=25.0, note="Thank you gift",
    ))

    # Contribution should still be returned successfully
    assert result["values"][0]["id"] == 101
    # Warning should be present
    assert "note_warning" in result
    assert "Note storage error" in result["note_warning"]
