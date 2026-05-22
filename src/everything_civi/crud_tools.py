import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_crud_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_get(
        entity: str,
        select: list[str] | None = None,
        where: list[list] | None = None,
        order_by: dict[str, str] | None = None,
        limit: int = 25,
        offset: int = 0,
        join: list[list] | None = None,
        group_by: list[str] | None = None,
        having: list[list] | None = None,
    ) -> str:
        """Query any CiviCRM entity with SQL-like filtering, joins, and aggregation.

        Examples:
          - Get all individual contacts:
            entity="Contact", where=[["contact_type", "=", "Individual"]]
          - Search with joins:
            entity="Contact", select=["display_name", "email.email"],
            join=[["Email AS email", "LEFT", null, ["id", "=", "email.contact_id"]]]
          - Use pseudoconstants:
            select=["display_name", "gender_id:label"],
            where=[["gender_id:name", "=", "Female"]]
          - Aggregate:
            entity="Contribution", select=["contact_id", "SUM:total_amount"],
            group_by=["contact_id"], order_by={"SUM:total_amount": "DESC"}, limit=10
          - Implicit joins:
            entity="Contribution", select=["total_amount", "contact_id.display_name"]

        WHERE operators: =, !=, <, >, <=, >=, LIKE, NOT LIKE, IN, NOT IN,
          BETWEEN, NOT BETWEEN, IS NULL, IS NOT NULL, CONTAINS, NOT CONTAINS,
          IS EMPTY, IS NOT EMPTY, REGEXP, NOT REGEXP

        Pseudoconstant suffixes: :name, :label, :description on option fields
          (e.g. gender_id:name returns "Male" instead of 1).

        Args:
            entity: Entity name in CamelCase (Contact, Contribution, Event, Membership, etc.)
            select: Fields to return. Supports wildcards (*), pseudoconstants, implicit joins,
                and aggregate functions. Defaults to ["*"].
            where: Filter conditions as [field, operator, value] triples.
            order_by: Sort order mapping field names to "ASC" or "DESC".
            limit: Maximum records to return (default 25).
            offset: Number of records to skip for pagination.
            join: Explicit joins, each as [EntityName AS alias, JOIN_TYPE, bridge_or_null, ...on_clauses].
            group_by: Fields to group results by (use with aggregate functions in select).
            having: Conditions on aggregated values (same format as where).
        """
        params: dict[str, Any] = {
            "select": select or ["*"],
            "limit": limit,
            "offset": offset,
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

        try:
            result = await client.api4(entity, "get", params)
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def civicrm_create(
        entity: str,
        values: dict[str, Any],
    ) -> str:
        """Create a single record of any CiviCRM entity.

        Examples:
          - Create a contact:
            entity="Contact", values={"contact_type": "Individual", "first_name": "Alice", "last_name": "Smith"}
          - Create with pseudoconstant:
            entity="Activity", values={"activity_type_id:name": "Meeting", "subject": "Team sync"}
          - Create a contribution:
            entity="Contribution", values={"contact_id": 42, "total_amount": 100.00,
            "financial_type_id:name": "Donation"}

        Pseudoconstant writes: use :name suffix to set option values by name instead of ID
          (e.g. activity_type_id:name = "Meeting").

        Args:
            entity: Entity name in CamelCase (Contact, Contribution, Activity, etc.)
            values: Field values for the new record.
        """
        try:
            result = await client.api4(entity, "create", {"values": values})
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def civicrm_update(
        entity: str,
        values: dict[str, Any],
        where: list[list],
        limit: int | None = None,
    ) -> str:
        """Update one or more records of any CiviCRM entity.

        The where clause is required to prevent accidental mass updates.

        Examples:
          - Update a contact by ID:
            entity="Contact", values={"first_name": "Bob"}, where=[["id", "=", 42]]
          - Update multiple records:
            entity="Participant", values={"status_id:name": "Registered"},
            where=[["event_id", "=", 10], ["status_id:name", "=", "Pending"]]

        Args:
            entity: Entity name in CamelCase.
            values: Fields to update with their new values.
            where: Filter conditions identifying which records to update (required).
            limit: Optional maximum number of records to update.
        """
        if not where:
            raise ValueError(
                "where clause is required for update operations to prevent "
                "accidental mass updates. Provide at least one condition."
            )

        params: dict[str, Any] = {"values": values, "where": where}
        if limit is not None:
            params["limit"] = limit

        try:
            result = await client.api4(entity, "update", params)
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def civicrm_delete(
        entity: str,
        where: list[list],
        use_trash: bool = True,
    ) -> str:
        """Delete records of any CiviCRM entity.

        The where clause is required to prevent accidental mass deletion.

        By default, entities that support soft-delete (like Contact) are moved to
        trash. Set use_trash=False to permanently delete.

        Examples:
          - Soft-delete a contact:
            entity="Contact", where=[["id", "=", 42]]
          - Permanently delete:
            entity="Contact", where=[["id", "=", 42]], use_trash=False
          - Delete activities by type:
            entity="Activity", where=[["activity_type_id:name", "=", "Bulk Email"], ["is_deleted", "=", True]]

        Args:
            entity: Entity name in CamelCase.
            where: Filter conditions identifying which records to delete (required).
            use_trash: If True (default), soft-delete entities that support it.
                Set to False for permanent deletion.
        """
        if not where:
            raise ValueError(
                "where clause is required for delete operations to prevent "
                "accidental mass deletion. Provide at least one condition."
            )

        params: dict[str, Any] = {"where": where, "useTrash": use_trash}

        try:
            result = await client.api4(entity, "delete", params)
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def civicrm_save(
        entity: str,
        records: list[dict[str, Any]],
        match: list[str] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> str:
        """Batch create-or-update (upsert) records of any CiviCRM entity.

        Records with an "id" field are updated; records without "id" are created.
        Use the match parameter to upsert by fields other than id.

        Examples:
          - Upsert contacts by external_id:
            entity="Contact", records=[{"external_id": "EXT-001", "first_name": "Alice"},
            {"external_id": "EXT-002", "first_name": "Bob"}], match=["external_id"]
          - Batch create with defaults:
            entity="Activity", records=[{"subject": "Call 1"}, {"subject": "Call 2"}],
            defaults={"activity_type_id:name": "Phone Call", "status_id:name": "Completed"}
          - Mixed create and update:
            entity="Contact", records=[{"id": 42, "last_name": "Updated"},
            {"first_name": "New", "last_name": "Contact", "contact_type": "Individual"}]

        Args:
            entity: Entity name in CamelCase.
            records: List of record dicts. Include "id" to update existing records.
            match: Fields to match on for upsert (e.g. ["external_id"]).
                When set, existing records matching these fields are updated instead of creating duplicates.
            defaults: Default values applied to newly created records (not applied to updates).
        """
        params: dict[str, Any] = {"records": records}
        if match is not None:
            params["match"] = match
        if defaults is not None:
            params["defaults"] = defaults

        try:
            result = await client.api4(entity, "save", params)
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)

    @mcp.tool()
    async def civicrm_replace(
        entity: str,
        records: list[dict[str, Any]],
        where: list[list],
    ) -> str:
        """Replace a set of records for any CiviCRM entity.

        Compares the provided records against existing records matching the where
        clause. Records that match are updated, new records are created, and
        existing records not in the provided set are deleted.

        This is useful for managing child records (e.g., replacing all phone numbers
        for a contact, or all line items for a contribution).

        Examples:
          - Replace all phone numbers for a contact:
            entity="Phone", where=[["contact_id", "=", 42]],
            records=[{"phone": "555-0100", "location_type_id": 1},
            {"phone": "555-0200", "location_type_id": 2}]
          - Replace email addresses:
            entity="Email", where=[["contact_id", "=", 42]],
            records=[{"email": "new@example.com", "is_primary": True}]

        Args:
            entity: Entity name in CamelCase.
            records: The complete new set of records.
            where: Conditions identifying the existing record set to replace.
        """
        if not where:
            raise ValueError(
                "where clause is required for replace operations to prevent "
                "accidental replacement of all records. Provide at least one condition."
            )

        params: dict[str, Any] = {"records": records, "where": where}

        try:
            result = await client.api4(entity, "replace", params)
        except CiviCRMAPIError as e:
            return str(e)

        return json.dumps(result, indent=2)
