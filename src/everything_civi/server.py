import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from everything_civi.admin_tools import register_admin_tools
from everything_civi.client import CiviCRMClient
from everything_civi.config import CiviCRMConfig
from everything_civi.logging_config import setup_logging
from everything_civi.crud_tools import register_crud_tools
from everything_civi.discovery_tools import register_discovery_tools
from everything_civi.prompts import register_prompts
from everything_civi.resources import register_resources
from everything_civi.searchkit_tools import register_searchkit_tools
from everything_civi.utility_tools import register_utility_tools
from everything_civi.workflow_tools import register_workflow_tools

logger = logging.getLogger("everything_civi.server")

config = CiviCRMConfig()
setup_logging(config.log_level)
client = CiviCRMClient(config)


@asynccontextmanager
async def lifespan(server):
    yield
    await client.close()


mcp = FastMCP(
    "everything-civi",
    instructions="MCP server for complete CiviCRM operations — contacts, activities, contributions, memberships, events, and more.",
    lifespan=lifespan,
)

register_crud_tools(mcp, client)
register_discovery_tools(mcp, client)
register_workflow_tools(mcp, client)
register_searchkit_tools(mcp, client)
register_utility_tools(mcp, client)
register_admin_tools(mcp, client)
register_resources(mcp, client)
register_prompts(mcp)

allowed = config.get_allowed_tools()
if allowed is not None:
    registered_names = set(mcp._tool_manager._tools.keys())
    unknown = allowed - registered_names
    if unknown:
        logger.warning("Allowlist contains unknown tool names: %s", unknown)
    for name in list(registered_names):
        if name not in allowed:
            del mcp._tool_manager._tools[name]
    if not mcp._tool_manager._tools:
        logger.error("All tools pruned by allowlist — no tools available")


def main():
    mcp.run()
