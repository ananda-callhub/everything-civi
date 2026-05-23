import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_utility_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_paginate(
        entity: str,
        select: list[str] | None = None,
        where: list[list] | None = None,
        order_by: dict[str, str] | None = None,
        join: list[list] | None = None,
        group_by: list[str] | None = None,
        having: list[list] | None = None,
        page_size: int = 100,
        max_records: int = 1000,
    ) -> str:
        """Auto-paginate through large CiviCRM result sets, combining all pages.

        Fetches records in batches of page_size, accumulating results until either
        a page returns fewer than page_size records (end of data) or max_records
        is reached (safety cap). Returns all fetched records with pagination metadata.

        Use this instead of civicrm_get when you need more than 25 records or want
        to iterate through an entire result set without manual offset management.

        Examples:
          - Get all active members:
            entity="Membership", where=[["status_id:name", "IN", ["New", "Current"]]]
          - Export contacts with emails:
            entity="Contact", select=["display_name", "email.email"],
            join=[["Email AS email", "LEFT", null, ["id", "=", "email.contact_id"]]],
            max_records=5000
          - Paginate contributions by date:
            entity="Contribution", select=["contact_id", "total_amount", "receive_date"],
            order_by={"receive_date": "DESC"}, page_size=50, max_records=500

        Args:
            entity: Entity name in CamelCase (Contact, Contribution, Event, etc.)
            select: Fields to return. Defaults to ["*"].
            where: Filter conditions as [field, operator, value] triples.
            order_by: Sort order mapping field names to "ASC" or "DESC".
            join: Explicit joins, each as [EntityName AS alias, JOIN_TYPE, bridge_or_null, ...on_clauses].
            group_by: Fields to group results by.
            having: Conditions on aggregated values (same format as where).
            page_size: Records per API call (default 100).
            max_records: Safety cap to prevent runaway fetches (default 1000).
        """
        try:
            params: dict[str, Any] = {
                "select": select or ["*"],
            }
            if where is not None:
                params["where"] = where
            if order_by is not None:
                params["orderBy"] = order_by
            if join is not None:
                params["join"] = join
            if group_by is not None:
                params["groupBy"] = group_by
            if having is not None:
                params["having"] = having

            all_values: list[dict[str, Any]] = []
            offset = 0
            pages = 0

            while len(all_values) < max_records:
                effective_limit = min(page_size, max_records - len(all_values))
                if effective_limit <= 0:
                    break
                params["limit"] = effective_limit
                params["offset"] = offset

                result = await client.api4(entity, "get", params)
                page = result.get("values", [])
                pages += 1
                all_values.extend(page)

                if len(page) < params["limit"]:
                    break

                offset += len(page)

            truncated = len(all_values) >= max_records

            return json.dumps({
                "values": all_values,
                "total_fetched": len(all_values),
                "pages": pages,
                "truncated": truncated,
            }, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error paginating {entity}: {exc}"

    @mcp.tool()
    async def civicrm_bulk_import(
        entity: str,
        records: list[dict[str, Any]],
        match: list[str] | None = None,
        defaults: dict[str, Any] | None = None,
        batch_size: int = 50,
    ) -> str:
        """Batch import records into CiviCRM with upsert semantics and per-batch error reporting.

        Splits records into batches and uses the save action (create-or-update) for each batch.
        If a batch fails, the error is captured but remaining batches continue processing.

        Use this for bulk data loading — contacts, contributions, memberships, etc.
        The match parameter controls upsert behavior: matched records are updated,
        unmatched records are created.

        Examples:
          - Import contacts with dedup on external_identifier:
            entity="Contact", records=[{"contact_type": "Individual", "first_name": "Alice",
            "external_identifier": "EXT-001"}, ...], match=["external_identifier"]
          - Bulk create activities with defaults:
            entity="Activity", records=[{"subject": "Call 1"}, {"subject": "Call 2"}],
            defaults={"activity_type_id:name": "Phone Call", "status_id:name": "Completed"}
          - Import with email-based matching:
            entity="Contact", records=[...], match=["email"]

        Args:
            entity: Entity name in CamelCase.
            records: List of record dicts to import.
            match: Fields to match on for upsert (e.g. ["external_identifier"]).
                When set, existing records matching these fields are updated.
            defaults: Default values applied to newly created records.
            batch_size: Records per API call (default 50).
        """
        total_records = len(records)
        batches_processed = 0
        successful_records = 0
        failed_batches: list[dict[str, Any]] = []
        all_results: list[dict[str, Any]] = []

        for i in range(0, total_records, batch_size):
            batch = records[i:i + batch_size]
            batch_number = (i // batch_size) + 1

            params: dict[str, Any] = {"records": batch}
            if match is not None:
                params["match"] = match
            if defaults is not None:
                params["defaults"] = defaults

            try:
                result = await client.api4(entity, "save", params)
                saved = result.get("values", [])
                successful_records += len(saved)
                all_results.extend(saved)
            except CiviCRMAPIError as exc:
                failed_batches.append({
                    "batch": batch_number,
                    "start_index": i,
                    "end_index": min(i + batch_size, len(records)),
                    "error": str(exc),
                })

            batches_processed += 1

        return json.dumps({
            "entity": entity,
            "total_records": total_records,
            "batches_processed": batches_processed,
            "successful_records": successful_records,
            "failed_batches": failed_batches,
            "results": all_results,
        }, indent=2)

    @mcp.tool()
    async def civicrm_find_or_create_contact(
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        contact_type: str = "Individual",
        organization_name: str | None = None,
        external_identifier: str | None = None,
        phone: str | None = None,
        additional_values: dict[str, Any] | None = None,
    ) -> str:
        """Find an existing contact by email, external_identifier, or name — or create one.

        Searches using the best available identifier in priority order:
        external_identifier > email > organization_name > first_name + last_name.
        If found, returns the existing contact. If not found, creates a new contact
        with all provided fields and linked Email/Phone records.

        Note: not transactionally safe under concurrent access. If multiple calls
        race for the same contact, duplicates may be created. For guaranteed dedup,
        use civicrm_save with match fields instead.

        Examples:
          - Find or create by email:
            email="alice@example.com", first_name="Alice", last_name="Smith"
          - Find or create organization:
            contact_type="Organization", organization_name="Acme Corp",
            email="info@acme.com"
          - With extra fields:
            email="bob@example.com", first_name="Bob", last_name="Jones",
            additional_values={"job_title": "Director", "employer_id": 42}

        Args:
            email: Email address for searching and creation.
            first_name: First name (for Individual contacts).
            last_name: Last name (for Individual contacts).
            contact_type: Contact type: "Individual" (default), "Organization", or "Household".
            organization_name: Organization name (required for Organization contacts).
            external_identifier: External system identifier for matching.
            phone: Phone number to add on creation.
            additional_values: Extra field values to set when creating (not used for search).
                These values take precedence over other parameters if keys overlap.
        """
        try:
            # Validate: need at least one search criterion
            has_search = (
                external_identifier is not None
                or email is not None
                or organization_name is not None
                or (first_name is not None and last_name is not None)
            )
            if not has_search:
                return json.dumps({
                    "error": "Provide at least one search criterion: email, "
                    "external_identifier, organization_name, or first_name + last_name.",
                })

            if contact_type == "Organization" and organization_name is None:
                return json.dumps({
                    "error": "organization_name is required for Organization contacts.",
                })

            # Search in priority order
            found_contact = None

            # Priority 1: external_identifier
            if external_identifier is not None and found_contact is None:
                result = await client.api4("Contact", "get", {
                    "select": ["*"],
                    "where": [
                        ["external_identifier", "=", external_identifier],
                        ["contact_type", "=", contact_type],
                    ],
                    "limit": 1,
                })
                if result.get("values"):
                    found_contact = result["values"][0]

            # Priority 2: email (join to Email entity)
            if email is not None and found_contact is None:
                result = await client.api4("Contact", "get", {
                    "select": ["*", "e.email"],
                    "join": [
                        ["Email AS e", "INNER", None,
                         ["e.contact_id", "=", "id"]],
                    ],
                    "where": [
                        ["e.email", "=", email],
                        ["contact_type", "=", contact_type],
                    ],
                    "limit": 1,
                })
                if result.get("values"):
                    found_contact = result["values"][0]

            # Priority 3: organization_name (for Organization type)
            if (
                organization_name is not None
                and contact_type == "Organization"
                and found_contact is None
            ):
                result = await client.api4("Contact", "get", {
                    "select": ["*"],
                    "where": [
                        ["organization_name", "=", organization_name],
                        ["contact_type", "=", "Organization"],
                    ],
                    "limit": 1,
                })
                if result.get("values"):
                    found_contact = result["values"][0]

            # Priority 4: first_name + last_name
            if (
                first_name is not None
                and last_name is not None
                and found_contact is None
            ):
                result = await client.api4("Contact", "get", {
                    "select": ["*"],
                    "where": [
                        ["first_name", "=", first_name],
                        ["last_name", "=", last_name],
                        ["contact_type", "=", contact_type],
                    ],
                    "limit": 1,
                })
                if result.get("values"):
                    found_contact = result["values"][0]

            if found_contact is not None:
                return json.dumps({
                    "action": "found",
                    "contact": found_contact,
                }, indent=2)

            # Not found — create the contact
            values: dict[str, Any] = {"contact_type": contact_type}
            if first_name is not None:
                values["first_name"] = first_name
            if last_name is not None:
                values["last_name"] = last_name
            if organization_name is not None:
                values["organization_name"] = organization_name
            if external_identifier is not None:
                values["external_identifier"] = external_identifier
            if additional_values is not None:
                values.update(additional_values)

            create_result = await client.api4("Contact", "create", {"values": values})
            new_contact = create_result.get("values", [{}])[0]
            contact_id = new_contact.get("id")

            if not contact_id:
                return json.dumps({"error": "Contact creation returned no ID.", "action": "failed"})

            # Create linked Email record
            if email is not None and contact_id:
                await client.api4("Email", "create", {"values": {
                    "contact_id": contact_id,
                    "email": email,
                    "is_primary": True,
                    "location_type_id": 1,
                }})

            # Create linked Phone record
            if phone is not None and contact_id:
                await client.api4("Phone", "create", {"values": {
                    "contact_id": contact_id,
                    "phone": phone,
                    "is_primary": True,
                    "location_type_id": 1,
                }})

            return json.dumps({
                "action": "created",
                "contact": new_contact,
            }, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error in find_or_create_contact: {exc}"
