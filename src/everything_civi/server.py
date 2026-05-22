from mcp.server.fastmcp import FastMCP

from everything_civi.client import CiviCRMClient
from everything_civi.config import CiviCRMConfig
from everything_civi.crud_tools import register_crud_tools
from everything_civi.discovery_tools import register_discovery_tools
from everything_civi.resources import register_resources

config = CiviCRMConfig()
client = CiviCRMClient(config)

mcp = FastMCP(
    "everything-civi",
    instructions="MCP server for complete CiviCRM operations — contacts, activities, contributions, memberships, events, and more.",
)

register_crud_tools(mcp, client)
register_discovery_tools(mcp, client)
register_resources(mcp, client)


def main():
    mcp.run()
