import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_searchkit_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_list_saved_searches() -> str:
        """List all saved searches available on the CiviCRM instance.

        Returns each search's id, name, label, description, base entity,
        and timestamps.  Use the name value with civicrm_run_saved_search()
        or civicrm_describe_saved_search() to interact with a specific search.
        """
        try:
            result = await client.api4("SavedSearch", "get", {
                "select": [
                    "id",
                    "name",
                    "label",
                    "description",
                    "api_entity",
                    "created_date",
                    "modified_date",
                ],
            })
            return json.dumps(result.get("values", []), indent=2)
        except CiviCRMAPIError as exc:
            return f"Error listing saved searches: {exc}"

    @mcp.tool()
    async def civicrm_run_saved_search(
        saved_search: str,
        display: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: list[list[str]] | None = None,
    ) -> str:
        """Execute a saved search and return its results.

        Runs a SearchKit saved search through a display (table, list, or grid).
        If no display is specified, the first available display for the search
        is used automatically.

        Examples:
          - Run with defaults:
            saved_search="my_contact_list"
          - Paginate:
            saved_search="my_contact_list", limit=25, offset=50
          - Sort results:
            saved_search="my_contact_list", sort=[["display_name", "ASC"]]
          - Apply runtime filters:
            saved_search="my_contact_list", filters={"contact_type": "Individual"}

        Args:
            saved_search: Name of the saved search (use civicrm_list_saved_searches()
                to find available names).
            display: Display name to render through. If None, the first display
                associated with this search is used.
            filters: Runtime filter overrides as {field: value} pairs. These
                override any default filter values configured on the display.
            limit: Maximum results per page (default 50).
            offset: Number of results to skip for pagination (default 0).
            sort: Sort order as [[field, direction], ...] where direction is
                "ASC" or "DESC". Example: [["created_date", "DESC"]].
        """
        try:
            # If no display provided, look up the first display for this search
            if display is None:
                display_result = await client.api4("SearchDisplay", "get", {
                    "select": ["name"],
                    "where": [["saved_search_id.name", "=", saved_search]],
                    "limit": 1,
                })
                displays = display_result.get("values", [])
                if not displays:
                    return json.dumps({
                        "error": (
                            f"No display found for saved search '{saved_search}'. "
                            "Use civicrm_describe_saved_search() to inspect the search, "
                            "or civicrm_list_saved_searches() to verify the name."
                        ),
                    })
                display = displays[0]["name"]

            params: dict[str, Any] = {
                "savedSearch": saved_search,
                "display": display,
                "limit": limit,
                "offset": offset,
                "return": "page",
            }
            if filters is not None:
                params["filters"] = filters
            if sort is not None:
                params["sort"] = sort

            result = await client.api4("SearchDisplay", "run", params)

            return json.dumps({
                "values": result.get("values", []),
                "count": result.get("count", 0),
                "labels": result.get("labels", []),
            }, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error running saved search: {exc}"

    @mcp.tool()
    async def civicrm_describe_saved_search(
        saved_search: str,
    ) -> str:
        """Get full details of a saved search including its query definition and displays.

        Returns the search's base entity, API parameters (filters, joins,
        aggregations), and all associated displays with their types and names.

        Useful for understanding what a search does before running it, or for
        discovering which display names are available for civicrm_run_saved_search().

        Args:
            saved_search: Name or label of the saved search. Exact name match is
                tried first; if that fails, a fuzzy match on label is attempted.
        """
        try:
            # Try exact name match first
            result = await client.api4("SavedSearch", "get", {
                "select": [
                    "id",
                    "name",
                    "label",
                    "description",
                    "api_entity",
                    "api_params",
                    "created_date",
                    "modified_date",
                    "expires_date",
                ],
                "where": [["name", "=", saved_search]],
                "limit": 1,
            })

            searches = result.get("values", [])

            # Fall back to fuzzy label match
            if not searches:
                escaped = saved_search.replace("%", r"\%").replace("_", r"\_")
                result = await client.api4("SavedSearch", "get", {
                    "select": [
                        "id",
                        "name",
                        "label",
                        "description",
                        "api_entity",
                        "api_params",
                        "created_date",
                        "modified_date",
                        "expires_date",
                    ],
                    "where": [["label", "LIKE", f"%{escaped}%"]],
                    "limit": 1,
                })
                searches = result.get("values", [])

            if not searches:
                return json.dumps({
                    "error": (
                        f"No saved search found matching '{saved_search}'. "
                        "Use civicrm_list_saved_searches() to see available searches."
                    ),
                })

            search = searches[0]
            search_id = search["id"]

            # Fetch associated displays
            displays_result = await client.api4("SearchDisplay", "get", {
                "select": ["id", "name", "label", "type"],
                "where": [["saved_search_id", "=", search_id]],
            })

            return json.dumps({
                "search": search,
                "displays": displays_result.get("values", []),
            }, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error describing saved search: {exc}"
