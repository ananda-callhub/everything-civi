import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_workflow_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_search_contacts(
        query: str,
        contact_type: str | None = None,
        limit: int = 10,
    ) -> str:
        """Search contacts across name, email, and phone in one call.

        Returns enriched results with primary email and phone included.
        The query is matched against display_name, email, and phone using
        fuzzy (LIKE) matching.

        Args:
            query: Search text to match against name, email, or phone.
            contact_type: Optional filter: "Individual", "Organization", or "Household".
            limit: Maximum results (default 10).
        """
        try:
            escaped_query = query.replace("%", r"\%").replace("_", r"\_")
            where: list[Any] = [
                ["OR", [
                    ["display_name", "LIKE", f"%{escaped_query}%"],
                    ["e.email", "LIKE", f"%{escaped_query}%"],
                    ["p.phone", "LIKE", f"%{escaped_query}%"],
                ]],
                ["is_deleted", "=", False],
            ]
            if contact_type:
                where.append(["contact_type", "=", contact_type])

            result = await client.api4("Contact", "get", {
                "select": [
                    "id", "contact_type", "display_name",
                    "first_name", "last_name",
                    "e.email", "p.phone",
                ],
                "join": [
                    ["Email AS e", "LEFT", None,
                     ["e.contact_id", "=", "id"],
                     ["e.is_primary", "=", True]],
                    ["Phone AS p", "LEFT", None,
                     ["p.contact_id", "=", "id"],
                     ["p.is_primary", "=", True]],
                ],
                "where": where,
                "groupBy": ["id"],
                "orderBy": {"sort_name": "ASC"},
                "limit": limit,
            })
            return json.dumps(result.get("values", []), indent=2)
        except CiviCRMAPIError as exc:
            return f"Error searching contacts: {exc}"

    @mcp.tool()
    async def civicrm_record_contribution(
        contact_id: int,
        total_amount: float,
        financial_type: str = "Donation",
        receive_date: str | None = None,
        payment_instrument: str | None = None,
        source: str | None = None,
        note: str | None = None,
    ) -> str:
        """Record a contribution (donation, payment, fee) for a contact.

        Resolves financial_type by name and optionally attaches a note.

        Args:
            contact_id: The contact making the contribution.
            total_amount: Contribution amount.
            financial_type: Financial type name (default "Donation").
                Common types: "Donation", "Event Fee", "Member Dues", "Campaign Contribution".
            receive_date: Date received (YYYY-MM-DD). Defaults to today.
            payment_instrument: Payment method name, e.g. "Check", "Credit Card", "Cash", "EFT".
            source: Free-text source/reference.
            note: Optional note to attach to the contribution.
        """
        try:
            values: dict[str, Any] = {
                "contact_id": contact_id,
                "total_amount": total_amount,
                "financial_type_id:name": financial_type,
                "contribution_status_id:name": "Completed",
            }
            if receive_date:
                values["receive_date"] = receive_date
            if payment_instrument:
                values["payment_instrument_id:name"] = payment_instrument
            if source:
                values["source"] = source

            result = await client.api4("Contribution", "create", {"values": values})

            if note and result.get("values"):
                contribution_id = result["values"][0]["id"]
                try:
                    await client.api4("Note", "create", {"values": {
                        "entity_table": "civicrm_contribution",
                        "entity_id": contribution_id,
                        "note": note,
                        "contact_id": contact_id,
                    }})
                except CiviCRMAPIError as note_exc:
                    result["note_warning"] = (
                        f"Contribution created but note failed: {note_exc}"
                    )

            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error recording contribution: {exc}"

    @mcp.tool()
    async def civicrm_manage_membership(
        contact_id: int,
        membership_type: str,
        action: str = "create",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        """Create, renew, or cancel a membership for a contact.

        Resolves membership_type by name. For renew/cancel, finds the most
        recent matching membership automatically.

        Args:
            contact_id: The contact for the membership.
            membership_type: Membership type name (e.g. "General", "Student", "Lifetime").
            action: One of "create", "renew", or "cancel". Note: when renewing,
                provide end_date to extend the membership period, otherwise only the
                status changes.
            start_date: Start date (YYYY-MM-DD). Used for create and renew.
            end_date: End date (YYYY-MM-DD). Used for create and renew.
        """
        try:
            if action == "create":
                values: dict[str, Any] = {
                    "contact_id": contact_id,
                    "membership_type_id:name": membership_type,
                    "status_id:name": "New",
                }
                if start_date:
                    values["start_date"] = start_date
                if end_date:
                    values["end_date"] = end_date
                result = await client.api4("Membership", "create", {"values": values})

            elif action in ("renew", "cancel"):
                existing = await client.api4("Membership", "get", {
                    "where": [
                        ["contact_id", "=", contact_id],
                        ["membership_type_id:name", "=", membership_type],
                    ],
                    "orderBy": {"end_date": "DESC"},
                    "limit": 1,
                })
                if not existing.get("values"):
                    return json.dumps({
                        "error": f"No existing '{membership_type}' membership found for contact {contact_id}",
                    })

                membership_id = existing["values"][0]["id"]

                if action == "renew":
                    update_values: dict[str, Any] = {"status_id:name": "Current"}
                    if start_date:
                        update_values["start_date"] = start_date
                    if end_date:
                        update_values["end_date"] = end_date
                    result = await client.api4("Membership", "update", {
                        "values": update_values,
                        "where": [["id", "=", membership_id]],
                    })
                else:
                    result = await client.api4("Membership", "update", {
                        "values": {"status_id:name": "Cancelled"},
                        "where": [["id", "=", membership_id]],
                    })

            else:
                return json.dumps({
                    "error": f"Unknown action '{action}'. Use 'create', 'renew', or 'cancel'.",
                })

            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error managing membership: {exc}"

    @mcp.tool()
    async def civicrm_register_for_event(
        contact_id: int,
        event_id: int,
        status: str = "Registered",
        role: str = "Attendee",
        register_date: str | None = None,
        record_contribution: bool = False,
        contribution_amount: float | None = None,
    ) -> str:
        """Register a contact for an event, optionally recording payment.

        Creates a Participant record and optionally a linked Contribution
        with the event's financial type.

        Args:
            contact_id: Contact to register.
            event_id: Event to register for.
            status: Registration status (default "Registered").
            role: Participant role (default "Attendee").
            register_date: Registration date (YYYY-MM-DD). Defaults to today.
            record_contribution: If True, also create a Contribution for the fee.
            contribution_amount: Required if record_contribution is True.
        """
        try:
            # Validate inputs before any mutations
            if record_contribution and contribution_amount is None:
                return json.dumps({
                    "error": "contribution_amount is required when record_contribution is True",
                })

            participant_values: dict[str, Any] = {
                "contact_id": contact_id,
                "event_id": event_id,
                "status_id:name": status,
                "role_id:name": role,
            }
            if register_date:
                participant_values["register_date"] = register_date

            if not record_contribution:
                # Simple path: just create the participant
                participant_result = await client.api4(
                    "Participant", "create", {"values": participant_values},
                )
                return json.dumps({
                    "participant": participant_result.get("values", []),
                }, indent=2)

            # Contribution path: look up event financial type before any mutations
            event = await client.api4("Event", "get", {
                "select": ["title", "financial_type_id:name"],
                "where": [["id", "=", event_id]],
                "limit": 1,
            })
            if not event.get("values"):
                return json.dumps({"error": f"Event {event_id} not found"})
            financial_type = event["values"][0].get("financial_type_id:name") or "Event Fee"

            # Step 1: Create participant
            participant_result = await client.api4(
                "Participant", "create", {"values": participant_values},
            )
            if not participant_result.get("values"):
                return json.dumps({"error": "Participant creation returned no data"})
            participant_id = participant_result["values"][0]["id"]

            try:
                # Step 2: Create contribution
                contribution_result = await client.api4("Contribution", "create", {
                    "values": {
                        "contact_id": contact_id,
                        "total_amount": contribution_amount,
                        "financial_type_id:name": financial_type,
                        "contribution_status_id:name": "Completed",
                        "source": f"Event registration: Event {event_id}",
                    },
                })
                if not contribution_result.get("values"):
                    raise CiviCRMAPIError("Contribution creation returned no data")
                contribution_id = contribution_result["values"][0]["id"]
            except CiviCRMAPIError as contrib_exc:
                cleanup_warning = ""
                try:
                    await client.api4("Participant", "delete", {
                        "where": [["id", "=", participant_id]],
                        "useTrash": False,
                    })
                except CiviCRMAPIError as cleanup_exc:
                    cleanup_warning = f" WARNING: cleanup of participant {participant_id} also failed: {cleanup_exc}"
                raise CiviCRMAPIError(
                    f"Event registration rolled back — contribution failed: {contrib_exc}.{cleanup_warning}"
                ) from contrib_exc

            # Step 3: Link participant and contribution
            try:
                await client.api4("ParticipantPayment", "create", {"values": {
                    "participant_id": participant_id,
                    "contribution_id": contribution_id,
                }})
            except CiviCRMAPIError as link_exc:
                cleanup_warnings = []
                try:
                    await client.api4("Contribution", "delete", {
                        "where": [["id", "=", contribution_id]],
                    })
                except CiviCRMAPIError as ce:
                    cleanup_warnings.append(f"contribution {contribution_id}: {ce}")
                try:
                    await client.api4("Participant", "delete", {
                        "where": [["id", "=", participant_id]],
                        "useTrash": False,
                    })
                except CiviCRMAPIError as pe:
                    cleanup_warnings.append(f"participant {participant_id}: {pe}")
                warning_str = f" WARNING: cleanup failed for {', '.join(cleanup_warnings)}" if cleanup_warnings else ""
                raise CiviCRMAPIError(
                    f"Event registration rolled back — payment link failed: {link_exc}.{warning_str}"
                ) from link_exc

            return json.dumps({
                "participant": participant_result.get("values", []),
                "contribution": contribution_result.get("values", []),
            }, indent=2)

        except CiviCRMAPIError as exc:
            return f"Error registering for event: {exc}"

    @mcp.tool()
    async def civicrm_log_activity(
        activity_type: str,
        subject: str,
        source_contact_id: int,
        target_contact_ids: list[int] | None = None,
        assignee_contact_ids: list[int] | None = None,
        status: str = "Completed",
        details: str | None = None,
        activity_date: str | None = None,
        case_id: int | None = None,
    ) -> str:
        """Log an activity with proper contact role linkages.

        Creates an Activity record with source, target, and assignee contacts.
        Optionally links the activity to a case.

        Args:
            activity_type: Activity type name (e.g. "Meeting", "Phone Call", "Email",
                "Follow up", "Interview").
            subject: Activity subject line.
            source_contact_id: Contact who performed/initiated the activity.
            target_contact_ids: Contacts the activity is about.
            assignee_contact_ids: Contacts assigned to the activity.
            status: Activity status (default "Completed"). Options: "Scheduled",
                "Completed", "Cancelled", "Left Message", "Unreachable", "Not Required".
            details: HTML or plain-text body.
            activity_date: Date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS). Defaults to now.
            case_id: Optional case to link this activity to.
        """
        try:
            values: dict[str, Any] = {
                "activity_type_id:name": activity_type,
                "subject": subject,
                "source_contact_id": source_contact_id,
                "status_id:name": status,
            }
            if target_contact_ids:
                values["target_contact_id"] = target_contact_ids
            if assignee_contact_ids:
                values["assignee_contact_id"] = assignee_contact_ids
            if details:
                values["details"] = details
            if activity_date:
                values["activity_date_time"] = activity_date
            if case_id:
                values["case_id"] = case_id

            result = await client.api4("Activity", "create", {"values": values})
            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error logging activity: {exc}"

    @mcp.tool()
    async def civicrm_manage_group_contacts(
        contact_ids: list[int],
        group_id: int | None = None,
        group_title: str | None = None,
        action: str = "add",
    ) -> str:
        """Add or remove contacts from a group.

        Resolves group by title if group_id is not provided.
        Uses upsert (save with match) to avoid duplicates when adding.

        Args:
            contact_ids: List of contact IDs to add or remove.
            group_id: Group ID (provide this or group_title).
            group_title: Group title to look up (provide this or group_id).
            action: "add" or "remove".
        """
        try:
            if group_id is None and group_title is None:
                return json.dumps({"error": "Provide either group_id or group_title."})

            if group_title and group_id is None:
                group_result = await client.api4("Group", "get", {
                    "select": ["id", "title"],
                    "where": [["title", "=", group_title]],
                    "limit": 1,
                })
                if not group_result.get("values"):
                    return json.dumps({"error": f"Group '{group_title}' not found."})
                group_id = group_result["values"][0]["id"]

            if action == "add":
                records = [
                    {"contact_id": cid, "group_id": group_id, "status": "Added"}
                    for cid in contact_ids
                ]
                result = await client.api4("GroupContact", "save", {
                    "records": records,
                    "match": ["contact_id", "group_id"],
                })
            elif action == "remove":
                records = [
                    {"contact_id": cid, "group_id": group_id, "status": "Removed"}
                    for cid in contact_ids
                ]
                result = await client.api4("GroupContact", "save", {
                    "records": records,
                    "match": ["contact_id", "group_id"],
                })
            else:
                return json.dumps({
                    "error": f"Unknown action '{action}'. Use 'add' or 'remove'.",
                })

            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error managing group contacts: {exc}"

    @mcp.tool()
    async def civicrm_manage_relationship(
        contact_id_a: int,
        contact_id_b: int,
        relationship_type: str,
        action: str = "create",
        start_date: str | None = None,
        end_date: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create or deactivate a relationship between two contacts.

        Resolves relationship type by matching against both internal name (name_a_b) and display label (label_a_b).

        Args:
            contact_id_a: First contact (the "A" side, e.g. the employee).
            contact_id_b: Second contact (the "B" side, e.g. the employer).
            relationship_type: Relationship type label as seen from A's perspective
                (e.g. "Employee of", "Child of", "Spouse of", "Head of Household for").
            action: "create" or "disable".
            start_date: Relationship start date (YYYY-MM-DD).
            end_date: Relationship end date (YYYY-MM-DD).
            description: Free-text description.
        """
        try:
            type_result = await client.api4("RelationshipType", "get", {
                "select": ["id", "name_a_b", "name_b_a"],
                "where": [
                    ["OR", [
                        ["name_a_b", "=", relationship_type],
                        ["label_a_b", "=", relationship_type],
                    ]],
                ],
                "limit": 1,
            })
            if not type_result.get("values"):
                return json.dumps({
                    "error": f"Relationship type '{relationship_type}' not found.",
                })
            rel_type_id = type_result["values"][0]["id"]

            if action == "create":
                values: dict[str, Any] = {
                    "contact_id_a": contact_id_a,
                    "contact_id_b": contact_id_b,
                    "relationship_type_id": rel_type_id,
                    "is_active": True,
                }
                if start_date:
                    values["start_date"] = start_date
                if end_date:
                    values["end_date"] = end_date
                if description:
                    values["description"] = description
                result = await client.api4("Relationship", "create", {"values": values})

            elif action == "disable":
                existing = await client.api4("Relationship", "get", {
                    "where": [
                        ["contact_id_a", "=", contact_id_a],
                        ["contact_id_b", "=", contact_id_b],
                        ["relationship_type_id", "=", rel_type_id],
                        ["is_active", "=", True],
                    ],
                    "limit": 1,
                })
                if not existing.get("values"):
                    return json.dumps({
                        "error": "No active relationship found matching the criteria.",
                    })
                result = await client.api4("Relationship", "update", {
                    "values": {"is_active": False},
                    "where": [["id", "=", existing["values"][0]["id"]]],
                })
            else:
                return json.dumps({
                    "error": f"Unknown action '{action}'. Use 'create' or 'disable'.",
                })

            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error managing relationship: {exc}"

    @mcp.tool()
    async def civicrm_open_case(
        contact_id: int,
        case_type: str,
        subject: str,
        status: str = "Open",
        details: str | None = None,
        start_date: str | None = None,
    ) -> str:
        """Open a new case for a contact.

        Creates the case and links the contact automatically.

        Args:
            contact_id: The client/subject of the case.
            case_type: Case type name (e.g. "Housing Support", "Adult Day Care Referral").
                Use civicrm_explore_options("Case", "case_type_id") to list available types.
            subject: Brief description of the case.
            status: Case status (default "Open").
            details: Additional details.
            start_date: Case start date (YYYY-MM-DD). Defaults to today.
        """
        try:
            values: dict[str, Any] = {
                "case_type_id:name": case_type,
                "subject": subject,
                "status_id:name": status,
                "contact_id": contact_id,
            }
            if start_date:
                values["start_date"] = start_date
            if details:
                values["details"] = details

            result = await client.api4("Case", "create", {"values": values})
            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error opening case: {exc}"

    @mcp.tool()
    async def civicrm_add_tags(
        entity_id: int,
        tag_names: list[str],
        entity_table: str = "civicrm_contact",
    ) -> str:
        """Add tags to a contact (or other entity) by tag name.

        Creates tags that don't exist yet, then links them. Uses upsert to
        avoid duplicate tag assignments.

        Args:
            entity_id: ID of the entity to tag (e.g. contact ID).
            tag_names: List of tag names to apply.
            entity_table: Entity table (default "civicrm_contact"). Other options:
                "civicrm_activity", "civicrm_case".
        """
        try:
            existing_tags = await client.api4("Tag", "get", {
                "select": ["id", "name"],
                "where": [
                    ["name", "IN", tag_names],
                    ["used_for", "CONTAINS", entity_table],
                ],
            })
            existing_map = {t["name"]: t["id"] for t in existing_tags.get("values", [])}

            tag_ids = []
            for name in tag_names:
                if name in existing_map:
                    tag_ids.append(existing_map[name])
                else:
                    created = await client.api4("Tag", "create", {"values": {
                        "name": name,
                        "used_for": [entity_table],
                    }})
                    if created.get("values"):
                        tag_ids.append(created["values"][0]["id"])

            if not tag_ids:
                return json.dumps({"error": "No tags could be resolved or created."})

            records = [
                {"entity_table": entity_table, "entity_id": entity_id, "tag_id": tid}
                for tid in tag_ids
            ]
            result = await client.api4("EntityTag", "save", {
                "records": records,
                "match": ["entity_table", "entity_id", "tag_id"],
            })
            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error adding tags: {exc}"
