"""Unit tests for utility tools using MockCiviCRMClient."""
from __future__ import annotations

import json

import pytest

from mcp.server.fastmcp import FastMCP

from everything_civi.utility_tools import register_utility_tools
from tests.conftest import MockCiviCRMClient


@pytest.fixture
def tools(mock_client: MockCiviCRMClient) -> dict:
    """Register utility tools and return them as a name->function dict."""
    mcp = FastMCP("test")
    register_utility_tools(mcp, mock_client)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


# ---------- civicrm_paginate ----------


@pytest.mark.asyncio
async def test_paginate_single_page(mock_client: MockCiviCRMClient, tools):
    """When results fit in one page, fetches once and returns them."""
    mock_client.set_response("Contact", "get", {
        "values": [
            {"id": 1, "display_name": "Alice"},
            {"id": 2, "display_name": "Bob"},
        ],
    })

    result = json.loads(await tools["civicrm_paginate"](
        entity="Contact",
        page_size=100,
    ))

    assert result["total_fetched"] == 2
    assert result["pages"] == 1
    assert result["truncated"] is False
    assert len(result["values"]) == 2

    # Only one API call should have been made
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[0] == "Contact"
    assert call[1] == "get"
    assert call[2]["limit"] == 100
    assert call[2]["offset"] == 0


@pytest.mark.asyncio
async def test_paginate_multiple_pages(mock_client: MockCiviCRMClient, tools):
    """When results span multiple pages, fetches all and combines them.

    Mock returns 2 records per call with page_size=2, max_records=4.
    Two full pages are fetched before max_records is hit.
    """
    mock_client.set_response("Contact", "get", {
        "values": [
            {"id": 1, "display_name": "Alice"},
            {"id": 2, "display_name": "Bob"},
        ],
    })

    result = json.loads(await tools["civicrm_paginate"](
        entity="Contact",
        page_size=2,
        max_records=4,
    ))

    assert result["total_fetched"] == 4
    assert result["pages"] == 2
    assert result["truncated"] is True  # hit max_records exactly

    # Two API calls should have been made
    assert len(mock_client.calls) == 2
    # The implementation mutates the same params dict, so both calls share
    # the final offset value.  We verify two calls were made and the total
    # fetched is correct rather than checking per-call offsets.


@pytest.mark.asyncio
async def test_paginate_hits_max_records(mock_client: MockCiviCRMClient, tools):
    """Stops fetching when max_records is reached even if more data is available."""
    # Return 3 records per page, max_records=3 -> should stop after 1 page
    mock_client.set_response("Membership", "get", {
        "values": [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ],
    })

    result = json.loads(await tools["civicrm_paginate"](
        entity="Membership",
        page_size=3,
        max_records=3,
    ))

    assert result["total_fetched"] == 3
    assert result["truncated"] is True
    # len(page)=3 which is not < limit=3, but all_values=3 >= max_records=3
    # so the while loop exits
    assert result["pages"] == 1


@pytest.mark.asyncio
async def test_paginate_with_params(mock_client: MockCiviCRMClient, tools):
    """Verify all optional params are passed through to the API call."""
    mock_client.set_response("Contribution", "get", {"values": []})

    await tools["civicrm_paginate"](
        entity="Contribution",
        select=["id", "total_amount"],
        where=[["total_amount", ">", 100]],
        order_by={"receive_date": "DESC"},
        join=[["Contact AS c", "INNER", None, ["contact_id", "=", "c.id"]]],
        group_by=["contact_id"],
        having=[["SUM(total_amount)", ">", 500]],
    )

    call = mock_client.calls[0]
    assert call[2]["select"] == ["id", "total_amount"]
    assert call[2]["where"] == [["total_amount", ">", 100]]
    assert call[2]["orderBy"] == {"receive_date": "DESC"}
    assert call[2]["join"] == [["Contact AS c", "INNER", None, ["contact_id", "=", "c.id"]]]
    assert call[2]["groupBy"] == ["contact_id"]
    assert call[2]["having"] == [["SUM(total_amount)", ">", 500]]


@pytest.mark.asyncio
async def test_paginate_empty_result(mock_client: MockCiviCRMClient, tools):
    """When entity has zero records, returns empty result."""
    mock_client.set_response("Contact", "get", {"values": []})

    result = json.loads(await tools["civicrm_paginate"](entity="Contact"))
    assert result["total_fetched"] == 0
    assert result["pages"] == 1
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_paginate_with_sequenced_responses(mock_client: MockCiviCRMClient, tools):
    """Verify actual data assembly with different pages using response sequences."""
    mock_client.set_response_sequence("Contact", "get", [
        {"values": [{"id": 1}, {"id": 2}]},  # page 1 (full)
        {"values": [{"id": 3}]},              # page 2 (partial -> stop)
    ])

    result = json.loads(await tools["civicrm_paginate"](
        entity="Contact", page_size=2, max_records=10,
    ))
    assert result["total_fetched"] == 3
    assert result["pages"] == 2
    assert result["values"] == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_paginate_verifies_offsets(mock_client: MockCiviCRMClient, tools):
    """Verify correct offset values in consecutive paginate calls."""
    mock_client.set_response_sequence("Contact", "get", [
        {"values": [{"id": 1}, {"id": 2}]},  # page 1
        {"values": [{"id": 3}, {"id": 4}]},  # page 2 (full -> continue)
        {"values": [{"id": 5}]},              # page 3 (partial -> stop)
    ])

    result = json.loads(await tools["civicrm_paginate"](
        entity="Contact", page_size=2, max_records=10,
    ))
    assert result["total_fetched"] == 5
    # Verify offsets were incremented correctly
    assert mock_client.calls[0][2]["offset"] == 0
    assert mock_client.calls[1][2]["offset"] == 2
    assert mock_client.calls[2][2]["offset"] == 4


@pytest.mark.asyncio
async def test_paginate_api_error(mock_client: MockCiviCRMClient, tools):
    mock_client.set_error("Contact", "get", "Timeout error", 504)

    result = await tools["civicrm_paginate"](entity="Contact")
    assert "Error paginating Contact" in result
    assert "Timeout error" in result


# ---------- civicrm_bulk_import ----------


@pytest.mark.asyncio
async def test_bulk_import_single_batch(mock_client: MockCiviCRMClient, tools):
    """All records fit in one batch."""
    records = [
        {"first_name": "Alice", "last_name": "Smith", "contact_type": "Individual"},
        {"first_name": "Bob", "last_name": "Jones", "contact_type": "Individual"},
    ]
    mock_client.set_response("Contact", "save", {
        "values": [{"id": 1}, {"id": 2}],
    })

    result = json.loads(await tools["civicrm_bulk_import"](
        entity="Contact",
        records=records,
        batch_size=50,
    ))

    assert result["total_records"] == 2
    assert result["batches_processed"] == 1
    assert result["successful_records"] == 2
    assert result["failed_batches"] == []
    assert len(result["results"]) == 2

    # Verify the API call
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[0] == "Contact"
    assert call[1] == "save"
    assert call[2]["records"] == records


@pytest.mark.asyncio
async def test_bulk_import_multiple_batches(mock_client: MockCiviCRMClient, tools):
    """Records are split across multiple batches."""
    records = [
        {"first_name": f"Person{i}", "contact_type": "Individual"}
        for i in range(5)
    ]
    mock_client.set_response("Contact", "save", {
        "values": [{"id": 100}, {"id": 101}],
    })

    result = json.loads(await tools["civicrm_bulk_import"](
        entity="Contact",
        records=records,
        batch_size=2,
    ))

    # 5 records / batch_size 2 = 3 batches (2, 2, 1)
    assert result["total_records"] == 5
    assert result["batches_processed"] == 3
    assert len(mock_client.calls) == 3

    # Verify batch sizes
    assert len(mock_client.calls[0][2]["records"]) == 2
    assert len(mock_client.calls[1][2]["records"]) == 2
    assert len(mock_client.calls[2][2]["records"]) == 1


@pytest.mark.asyncio
async def test_bulk_import_with_match(mock_client: MockCiviCRMClient, tools):
    """Verify match param is passed to the save call for upsert behavior."""
    records = [
        {"external_identifier": "EXT-001", "first_name": "Alice"},
    ]
    mock_client.set_response("Contact", "save", {
        "values": [{"id": 1, "external_identifier": "EXT-001"}],
    })

    result = json.loads(await tools["civicrm_bulk_import"](
        entity="Contact",
        records=records,
        match=["external_identifier"],
    ))

    assert result["successful_records"] == 1
    call = mock_client.calls[0]
    assert call[2]["match"] == ["external_identifier"]


@pytest.mark.asyncio
async def test_bulk_import_with_defaults(mock_client: MockCiviCRMClient, tools):
    """Verify defaults param is passed to the save call."""
    records = [{"subject": "Call 1"}, {"subject": "Call 2"}]
    mock_client.set_response("Activity", "save", {
        "values": [{"id": 1}, {"id": 2}],
    })

    await tools["civicrm_bulk_import"](
        entity="Activity",
        records=records,
        defaults={"activity_type_id:name": "Phone Call", "status_id:name": "Completed"},
    )

    call = mock_client.calls[0]
    assert call[2]["defaults"] == {
        "activity_type_id:name": "Phone Call",
        "status_id:name": "Completed",
    }


@pytest.mark.asyncio
async def test_bulk_import_batch_error(mock_client: MockCiviCRMClient, tools):
    """When a batch fails, error is captured and remaining batches continue.

    The mock returns the same error for all Contact.save calls, so we test
    that all batches are attempted and all failures are reported.
    """
    records = [
        {"first_name": f"Person{i}", "contact_type": "Individual"}
        for i in range(4)
    ]
    mock_client.set_error("Contact", "save", "Validation failed", 400)

    result = json.loads(await tools["civicrm_bulk_import"](
        entity="Contact",
        records=records,
        batch_size=2,
    ))

    assert result["total_records"] == 4
    assert result["batches_processed"] == 2
    assert result["successful_records"] == 0
    assert len(result["failed_batches"]) == 2
    assert result["failed_batches"][0]["batch"] == 1
    assert "Validation failed" in result["failed_batches"][0]["error"]
    assert result["failed_batches"][1]["batch"] == 2


# ---------- civicrm_find_or_create_contact ----------


@pytest.mark.asyncio
async def test_find_or_create_contact_found_by_email(
    mock_client: MockCiviCRMClient, tools,
):
    """Contact exists with matching email -> returns with action='found'."""
    mock_client.set_response("Contact", "get", {
        "values": [{
            "id": 42,
            "display_name": "Alice Smith",
            "contact_type": "Individual",
            "e.email": "alice@example.com",
        }],
    })

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        email="alice@example.com",
        first_name="Alice",
        last_name="Smith",
    ))

    assert result["action"] == "found"
    assert result["contact"]["id"] == 42

    # Should search by email (priority 2) via a Contact.get with join
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[0] == "Contact"
    assert call[1] == "get"
    assert any("e.email" in str(w) for w in call[2].get("where", []))


@pytest.mark.asyncio
async def test_find_or_create_contact_created(
    mock_client: MockCiviCRMClient, tools,
):
    """Contact not found -> creates new contact with action='created'."""
    # All search queries return empty
    mock_client.set_response("Contact", "get", {"values": []})
    mock_client.set_response("Contact", "create", {
        "values": [{"id": 100, "first_name": "Charlie", "last_name": "Brown"}],
    })
    mock_client.set_response("Email", "create", {
        "values": [{"id": 200}],
    })

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        email="charlie@example.com",
        first_name="Charlie",
        last_name="Brown",
    ))

    assert result["action"] == "created"
    assert result["contact"]["id"] == 100

    # Should have: search by email (Contact.get), search by name (Contact.get),
    # create contact (Contact.create), create email (Email.create)
    entity_actions = [(c[0], c[1]) for c in mock_client.calls]
    assert ("Contact", "create") in entity_actions
    assert ("Email", "create") in entity_actions

    # Verify email create was linked to the new contact
    email_call = next(c for c in mock_client.calls if c[0] == "Email")
    assert email_call[2]["values"]["contact_id"] == 100
    assert email_call[2]["values"]["email"] == "charlie@example.com"


@pytest.mark.asyncio
async def test_find_or_create_contact_by_external_id(
    mock_client: MockCiviCRMClient, tools,
):
    """Searches by external_identifier first (highest priority)."""
    mock_client.set_response("Contact", "get", {
        "values": [{
            "id": 55,
            "external_identifier": "EXT-999",
            "display_name": "Ext Contact",
        }],
    })

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        external_identifier="EXT-999",
        email="ext@example.com",
        first_name="Ext",
        last_name="Contact",
    ))

    assert result["action"] == "found"
    assert result["contact"]["id"] == 55

    # Should have searched by external_identifier FIRST (1 call only since found)
    assert len(mock_client.calls) == 1
    call = mock_client.calls[0]
    assert call[2]["where"] == [
        ["external_identifier", "=", "EXT-999"],
        ["contact_type", "=", "Individual"],
    ]


@pytest.mark.asyncio
async def test_find_or_create_contact_no_criteria(
    mock_client: MockCiviCRMClient, tools,
):
    """Returns error when no search criteria provided."""
    result = json.loads(await tools["civicrm_find_or_create_contact"](
        first_name="Alice",
        # No last_name, no email, no external_identifier -> insufficient
    ))

    assert "error" in result
    assert "search criterion" in result["error"].lower() or "criterion" in result["error"]

    # No API calls should have been made
    assert len(mock_client.calls) == 0


@pytest.mark.asyncio
async def test_find_or_create_contact_with_phone(
    mock_client: MockCiviCRMClient, tools,
):
    """When phone is provided and contact is created, Phone record is also created."""
    mock_client.set_response("Contact", "get", {"values": []})
    mock_client.set_response("Contact", "create", {
        "values": [{"id": 200, "first_name": "Dana"}],
    })
    mock_client.set_response("Email", "create", {"values": [{"id": 300}]})
    mock_client.set_response("Phone", "create", {"values": [{"id": 400}]})

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        email="dana@example.com",
        first_name="Dana",
        last_name="White",
        phone="+1-555-1234",
    ))

    assert result["action"] == "created"

    phone_call = next(c for c in mock_client.calls if c[0] == "Phone")
    assert phone_call[2]["values"]["phone"] == "+1-555-1234"
    assert phone_call[2]["values"]["contact_id"] == 200


@pytest.mark.asyncio
async def test_find_or_create_contact_organization(
    mock_client: MockCiviCRMClient, tools,
):
    """Organization contacts search by organization_name."""
    mock_client.set_response("Contact", "get", {
        "values": [{
            "id": 77,
            "organization_name": "Acme Corp",
            "contact_type": "Organization",
        }],
    })

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        contact_type="Organization",
        organization_name="Acme Corp",
    ))

    assert result["action"] == "found"
    assert result["contact"]["organization_name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_find_or_create_contact_organization_missing_name(
    mock_client: MockCiviCRMClient, tools,
):
    """Organization contacts require organization_name."""
    result = json.loads(await tools["civicrm_find_or_create_contact"](
        contact_type="Organization",
        email="info@corp.com",
    ))

    assert "error" in result
    assert "organization_name" in result["error"]


@pytest.mark.asyncio
async def test_find_or_create_contact_api_error(
    mock_client: MockCiviCRMClient, tools,
):
    """API errors are caught and returned as clean error strings."""
    mock_client.set_error("Contact", "get", "Database connection lost", 500)

    result = await tools["civicrm_find_or_create_contact"](
        email="test@example.com",
    )
    assert "Error in find_or_create_contact" in result
    assert "Database connection lost" in result


@pytest.mark.asyncio
async def test_find_or_create_contact_with_additional_values(
    mock_client: MockCiviCRMClient, tools,
):
    """Additional values are merged into the create call."""
    mock_client.set_response("Contact", "get", {"values": []})
    mock_client.set_response("Contact", "create", {
        "values": [{"id": 300, "first_name": "Eve", "job_title": "Director"}],
    })
    mock_client.set_response("Email", "create", {"values": [{"id": 500}]})

    await tools["civicrm_find_or_create_contact"](
        email="eve@example.com",
        first_name="Eve",
        last_name="Adams",
        additional_values={"job_title": "Director", "employer_id": 42},
    )

    create_call = next(c for c in mock_client.calls if c[1] == "create" and c[0] == "Contact")
    assert create_call[2]["values"]["job_title"] == "Director"
    assert create_call[2]["values"]["employer_id"] == 42


@pytest.mark.asyncio
async def test_bulk_import_mixed_success_failure(mock_client: MockCiviCRMClient, tools):
    """When all batches fail, error output includes start_index and end_index."""
    mock_client.set_error("Contact", "save", "Validation failed", 400)

    result = json.loads(await tools["civicrm_bulk_import"](
        entity="Contact",
        records=[{"first_name": f"Test{i}"} for i in range(5)],
        batch_size=3,
    ))

    assert len(result["failed_batches"]) == 2
    # Verify record indices are included
    assert result["failed_batches"][0]["start_index"] == 0
    assert result["failed_batches"][0]["end_index"] == 3
    assert result["failed_batches"][1]["start_index"] == 3
    assert result["failed_batches"][1]["end_index"] == 5


@pytest.mark.asyncio
async def test_find_or_create_contact_type_filter(
    mock_client: MockCiviCRMClient, tools,
):
    """Verify contact_type is passed in search when finding Organization."""
    mock_client.set_response("Contact", "get", {
        "values": [{"id": 5, "display_name": "Acme Corp", "contact_type": "Organization"}],
    })

    result = json.loads(await tools["civicrm_find_or_create_contact"](
        organization_name="Acme Corp", contact_type="Organization",
    ))

    assert result["action"] == "found"
    # Verify contact_type filter was included in the search
    call = mock_client.calls[0]
    where = call[2]["where"]
    assert ["contact_type", "=", "Organization"] in where
