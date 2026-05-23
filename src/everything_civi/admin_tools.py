import json

from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMAPIError


def register_admin_tools(mcp: FastMCP, client) -> None:

    @mcp.tool()
    async def civicrm_system_status() -> str:
        """Check CiviCRM connectivity and system health.

        Returns connection status, CiviCRM version, CMS type, base URL,
        and any health-check warnings or errors. Use this to verify the
        server can reach CiviCRM and that the instance is healthy.
        """
        try:
            health = await client.health_check()

            # Try to get version info
            try:
                system_info = await client.api4("System", "get", {
                    "select": ["version", "uf", "baseUrl"],
                })
                info = (
                    system_info.get("values", [{}])[0]
                    if system_info.get("values")
                    else {}
                )
            except CiviCRMAPIError:
                info = {}

            result = {
                "connection": health.get("status", "unknown"),
                "civicrm_version": info.get("version"),
                "cms": info.get("uf"),
                "base_url": info.get("baseUrl"),
            }
            if health.get("checks"):
                # Filter to warnings/errors only
                issues = [
                    c for c in health["checks"]
                    if c.get("severity_id", 0) >= 3
                ]
                if issues:
                    result["warnings"] = issues
            if health.get("error"):
                result["error"] = health["error"]

            return json.dumps(result, indent=2)
        except CiviCRMAPIError as exc:
            return f"Error checking system status: {exc}"

    @mcp.tool()
    async def civicrm_system_flush() -> str:
        """Flush all CiviCRM system caches.

        Clears template, path, and data caches. Useful after making
        configuration changes or when data appears stale.
        """
        try:
            await client.api4("System", "flush", {})
            return json.dumps(
                {"status": "ok", "message": "Cache flush completed"},
                indent=2,
            )
        except CiviCRMAPIError as exc:
            return f"Error flushing cache: {exc}"
