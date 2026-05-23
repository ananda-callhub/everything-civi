from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMClient
from everything_civi.config import CiviCRMConfig
from everything_civi.crud_tools import register_crud_tools
from everything_civi.discovery_tools import register_discovery_tools
from everything_civi.prompts import register_prompts
from everything_civi.resources import register_resources
from everything_civi.searchkit_tools import register_searchkit_tools
from everything_civi.utility_tools import register_utility_tools
from everything_civi.workflow_tools import register_workflow_tools

config = CiviCRMConfig()
client = CiviCRMClient(config)

mcp = FastMCP(
    "everything-civi",
    instructions="MCP server for complete CiviCRM operations — contacts, activities, contributions, memberships, events, and more.",
)

register_crud_tools(mcp, client)
register_discovery_tools(mcp, client)
register_workflow_tools(mcp, client)
register_searchkit_tools(mcp, client)
register_utility_tools(mcp, client)
register_resources(mcp, client)
register_prompts(mcp)


def main():
    mcp.run()
