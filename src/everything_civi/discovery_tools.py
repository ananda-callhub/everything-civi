import json

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_discovery_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_list_entities() -> str:
        """List all CiviCRM entities available on the connected instance.

        Returns names, titles, descriptions, types, and other metadata for every
        entity the API exposes.  Useful for discovering what data types exist
        before querying or modifying records.
        """
        try:
            result = await client.api4(
                "Entity",
                "get",
                {
                    "select": [
                        "name",
                        "title",
                        "description",
                        "type",
                        "searchable",
                        "icon",
                    ],
                },
            )
            return json.dumps(result.get("values", result), indent=2)
        except CiviCRMAPIError as exc:
            return f"Error listing entities: {exc}"

    @mcp.tool()
    async def civicrm_describe_entity(
        entity: str,
        include_custom_fields: bool = True,
        action: str = "get",
    ) -> str:
        """Return the complete schema for a CiviCRM entity.

        Includes every field (name, data type, input type, whether required,
        foreign-key target, option list, readonly flag, serialisation format),
        plus the full list of actions the entity supports.

        Args:
            entity: Entity name, e.g. "Contact", "Contribution", "Activity".
            include_custom_fields: When True (default) custom field groups are
                included alongside core fields.
            action: The action whose field list to return.  Fields may differ
                between "get", "create", and "update".
        """
        try:
            fields_result = await client.get_fields(
                entity,
                action=action,
                load_options=["name", "label"],
            )
            actions_result = await client.api4(entity, "getActions", {})

            fields = []
            for f in fields_result.get("values", []):
                if not include_custom_fields and f.get("custom_group"):
                    continue
                fields.append({
                    "name": f.get("name"),
                    "title": f.get("title"),
                    "description": f.get("description"),
                    "data_type": f.get("data_type"),
                    "input_type": f.get("input_type"),
                    "required": f.get("required", False),
                    "fk_entity": f.get("fk_entity"),
                    "options": f.get("options") if f.get("options") else None,
                    "readonly": f.get("readonly", False),
                    "serialize": f.get("serialize"),
                })

            schema = {
                "entity": entity,
                "fields": fields,
                "actions": [
                    {"name": a.get("name"), "description": a.get("description")}
                    for a in actions_result.get("values", [])
                ],
            }
            return json.dumps(schema, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error describing entity '{entity}': {exc}"

    @mcp.tool()
    async def civicrm_explore_options(entity: str, field: str) -> str:
        """Return all valid option values for a field on a CiviCRM entity.

        Useful for understanding what values a field accepts -- for example,
        what contact types, activity types, contribution statuses, or gender
        options exist on this instance.

        Args:
            entity: Entity name, e.g. "Contact", "Activity".
            field: Field name, e.g. "gender_id", "contact_type",
                "activity_type_id", "contribution_status_id".
        """
        try:
            result = await client.api4(
                entity,
                "getFields",
                {
                    "where": [["name", "=", field]],
                    "loadOptions": ["id", "name", "label", "description"],
                    "action": "get",
                },
            )
            values = result.get("values", [])
            if not values:
                return json.dumps(
                    {"error": f"Field '{field}' not found on entity '{entity}'."},
                )
            options = values[0].get("options")
            if not options:
                return json.dumps(
                    {"error": f"Field '{field}' on '{entity}' has no option list."},
                )
            return json.dumps(options, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error exploring options for {entity}.{field}: {exc}"

    @mcp.tool()
    async def civicrm_check_access(
        entity: str,
        action: str,
        record_id: int | None = None,
    ) -> str:
        """Check whether the current API user has permission to perform an
        action on a CiviCRM entity.

        Args:
            entity: Entity name, e.g. "Contact", "Contribution".
            action: Action to check, e.g. "create", "delete", "update", "get".
            record_id: Optional ID of a specific record to check access for.
                When omitted the check applies to the entity in general.
        """
        try:
            params: dict = {
                "action": action,
                "values": {"id": record_id} if record_id else {},
            }
            result = await client.api4(entity, "checkAccess", params)
            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error checking access for {action} on {entity}: {exc}"

    @mcp.tool()
    async def civicrm_find_relationships(entity: str) -> str:
        """Discover how a CiviCRM entity relates to other entities via foreign
        keys.

        Returns every field that references another entity, showing which fields
        can be used for implicit joins (dot notation like
        ``contact_id.display_name``) and explicit joins in API queries.

        Args:
            entity: Entity to explore relationships for, e.g. "Contribution",
                "Participant", "Activity".
        """
        try:
            result = await client.get_fields(entity)
            relationships = []
            for f in result.get("values", []):
                fk = f.get("fk_entity")
                if fk:
                    relationships.append({
                        "field_name": f.get("name"),
                        "target_entity": fk,
                        "description": f.get("description"),
                    })
            return json.dumps(relationships, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error finding relationships for '{entity}': {exc}"
