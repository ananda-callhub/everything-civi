# everything-civi

MCP server for complete CiviCRM operations. Connect any AI assistant to your CiviCRM instance — manage contacts, contributions, memberships, events, cases, and all 150+ entities through a single integration.

## Features

- **28 tools** covering CRUD, discovery, workflows, SearchKit, bulk operations, and admin
- **3 MCP prompts** for guided CiviCRM administration, data import, and reporting
- **3 resources** with query construction guides and live entity listings
- Works with any CiviCRM 5.x instance (WordPress, Drupal, Joomla, Standalone)
- Compatible with Claude, OpenAI, Gemini, Cursor, VS Code, and any MCP client
- Retry with exponential backoff for transient errors
- Rate limiting to protect your CiviCRM instance
- Structured JSON audit logging with PII protection
- Tool permission allowlist for access control
- 142 tests (unit + integration)

## Quick Start

### Prerequisites

- Python 3.11+
- A CiviCRM instance with API key access
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
git clone https://github.com/ananda-callhub/everything-civi.git
cd everything-civi
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

### Configure

Copy the example environment file and fill in your CiviCRM credentials:

```bash
cp .env.example .env
```

```env
CIVICRM_BASE_URL=https://your-civicrm-site.org
CIVICRM_API_KEY=your-api-key-here
CIVICRM_VERIFY_SSL=true
CIVICRM_TIMEOUT=30
CIVICRM_MAX_RETRIES=2
CIVICRM_RETRY_DELAY=1.0
CIVICRM_MAX_CONCURRENT=5
CIVICRM_LOG_LEVEL=INFO
CIVICRM_AUDIT_LOG=true
CIVICRM_ALLOWED_TOOLS=
```

To generate an API key in CiviCRM: go to **Contacts > your admin contact > API Keys**, or run:

```bash
cv api4 Contact.update '{"where":[["id","=",YOUR_CONTACT_ID]],"values":{"api_key":"your-key-here"}}'
```

### Run

```bash
everything-civi
```

### Use with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "everything-civi": {
      "command": "/path/to/everything-civi/.venv/bin/everything-civi",
      "env": {
        "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
        "CIVICRM_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Use with Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "everything-civi": {
      "command": "/path/to/everything-civi/.venv/bin/everything-civi",
      "env": {
        "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
        "CIVICRM_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Use with OpenAI Agents SDK

```python
from agents import Agent
from agents.mcp import MCPServerStdio

async with MCPServerStdio(
    command="everything-civi",
    env={
        "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
        "CIVICRM_API_KEY": "your-api-key-here",
    },
) as mcp:
    agent = Agent(name="CiviCRM Assistant", mcp_servers=[mcp])
```

### Use with Cursor

Add to your Cursor MCP config (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "everything-civi": {
      "command": "/path/to/everything-civi/.venv/bin/everything-civi",
      "env": {
        "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
        "CIVICRM_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Use with VS Code / GitHub Copilot

Add to your VS Code settings (`.vscode/settings.json`):

```json
{
  "mcp": {
    "servers": {
      "everything-civi": {
        "command": "/path/to/everything-civi/.venv/bin/everything-civi",
        "env": {
          "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
          "CIVICRM_API_KEY": "your-api-key-here"
        }
      }
    }
  }
}
```

### Use with Gemini CLI

Add to your Gemini CLI settings (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "everything-civi": {
      "command": "/path/to/everything-civi/.venv/bin/everything-civi",
      "env": {
        "CIVICRM_BASE_URL": "https://your-civicrm-site.org",
        "CIVICRM_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Validate with MCP Inspector

Test your server interactively with the official MCP Inspector:

```bash
npx @anthropic-ai/mcp-inspector everything-civi
```

## Tools

### CRUD (6 tools)

Generic tools that work with any of CiviCRM's 150+ entities.

| Tool | Description |
|------|-------------|
| `civicrm_get` | Query any entity with filtering, joins, aggregation, and pagination |
| `civicrm_create` | Create a single record of any entity |
| `civicrm_update` | Update records matching a WHERE clause |
| `civicrm_delete` | Delete records (soft-delete by default) |
| `civicrm_save` | Batch create-or-update (upsert) with match fields |
| `civicrm_replace` | Replace a set of child records atomically |

### Discovery (5 tools)

Introspect the CiviCRM schema at runtime.

| Tool | Description |
|------|-------------|
| `civicrm_list_entities` | List all entities available on the instance |
| `civicrm_describe_entity` | Get full field schema, types, options, and actions for an entity |
| `civicrm_explore_options` | List all valid option values for a field |
| `civicrm_check_access` | Check API user permissions for an entity/action |
| `civicrm_find_relationships` | Discover foreign key relationships between entities |

### Workflow (9 tools)

Higher-level operations that chain multiple API calls with name resolution and validation.

| Tool | Description |
|------|-------------|
| `civicrm_search_contacts` | Smart search across name, email, and phone with enriched results |
| `civicrm_record_contribution` | Record a donation/payment with financial type resolution |
| `civicrm_manage_membership` | Create, renew, or cancel memberships with status-aware logic |
| `civicrm_register_for_event` | Register a contact for an event with optional payment |
| `civicrm_log_activity` | Log activities with proper source/target/assignee contact roles |
| `civicrm_manage_group_contacts` | Add or remove contacts from groups (with history preservation) |
| `civicrm_manage_relationship` | Create or disable relationships between contacts |
| `civicrm_open_case` | Open a case with automatic contact linkage |
| `civicrm_add_tags` | Tag contacts or other entities, creating missing tags automatically |

### SearchKit (3 tools)

Execute CiviCRM saved searches created through the SearchKit UI.

| Tool | Description |
|------|-------------|
| `civicrm_list_saved_searches` | List all saved searches on the instance |
| `civicrm_run_saved_search` | Execute a saved search with optional runtime filters |
| `civicrm_describe_saved_search` | Get search definition and available displays |

### Utility (3 tools)

Bulk operations and smart helpers.

| Tool | Description |
|------|-------------|
| `civicrm_paginate` | Auto-paginate through large result sets with a safety cap |
| `civicrm_bulk_import` | Batch import records with upsert and per-batch error recovery |
| `civicrm_find_or_create_contact` | Find existing contact by email/ID or create if not found |

### Admin (2 tools)

Server health and maintenance.

| Tool | Description |
|------|-------------|
| `civicrm_system_status` | Check CiviCRM connectivity, version, and health warnings |
| `civicrm_system_flush` | Flush all CiviCRM caches |

## Prompts

| Prompt | Description |
|--------|-------------|
| `civicrm_admin` | System prompt for general CiviCRM administration |
| `civicrm_data_import` | Guided workflow for importing data with validation and dedup |
| `civicrm_reporting` | Query construction and data analysis patterns |

## Resources

| URI | Description |
|-----|-------------|
| `civicrm://guide/querying` | Complete APIv4 query reference (WHERE operators, joins, aggregation) |
| `civicrm://guide/entities` | Entity relationship overview across all CiviCRM domains |
| `civicrm://entities` | Live list of entities on the connected instance |

## Configuration

All settings are configured via environment variables with the `CIVICRM_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `CIVICRM_BASE_URL` | (required) | Your CiviCRM instance URL |
| `CIVICRM_API_KEY` | (required) | API key for authentication |
| `CIVICRM_VERIFY_SSL` | `true` | Verify SSL certificates |
| `CIVICRM_TIMEOUT` | `30` | Request timeout in seconds |
| `CIVICRM_MAX_RETRIES` | `2` | Retries on transient errors (5xx, timeouts) |
| `CIVICRM_RETRY_DELAY` | `1.0` | Base delay for exponential backoff (seconds) |
| `CIVICRM_MAX_CONCURRENT` | `5` | Maximum concurrent API requests |
| `CIVICRM_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CIVICRM_AUDIT_LOG` | `true` | Enable structured JSON audit logging of API calls |
| `CIVICRM_ALLOWED_TOOLS` | (empty) | Comma-separated tool allowlist (empty = all tools) |

## Security and Enterprise Features

### Audit Logging

Every CiviCRM API call is logged as structured JSON to stdout with timestamp, entity, action, duration, and success/failure status:

```json
{"timestamp": "2026-05-23T14:30:00Z", "level": "INFO", "logger": "everything_civi.audit", "message": "api4_call", "entity": "Activity", "action": "get", "duration_ms": 42.5, "status": "success", "param_keys": ["select", "where", "limit"]}
```

PII protection is built in — sensitive entities (Contact, Email, Phone, Address, Contribution, Case, and others) have their parameter keys and error messages redacted in logs. You will never see personal data in audit output.

Control via environment variables:

```env
CIVICRM_AUDIT_LOG=true       # Enable/disable audit logging (default: true)
CIVICRM_LOG_LEVEL=INFO       # Logging level: DEBUG, INFO, WARNING, ERROR
```

### Tool Permission Allowlist

Restrict which tools are exposed to MCP clients. When set, only the listed tools are available — all others are removed at startup:

```env
CIVICRM_ALLOWED_TOOLS=civicrm_get,civicrm_list_entities,civicrm_describe_entity,civicrm_search_contacts
```

When empty or unset, all 28 tools are available (default). Resources and prompts are not filtered.

The server logs warnings for unrecognized tool names and errors if the allowlist results in zero available tools.

This is a defense-in-depth measure — CiviCRM also enforces its own permission model server-side based on the authenticated user's roles.

### Per-Request JWT Auth Forwarding

The client supports per-request token overrides for multi-user deployments. Instead of a single static API key, each API call can carry a different Bearer token:

```python
# Default: uses CIVICRM_API_KEY from config
result = await client.api4("Contact", "get", params)

# Override: uses a per-user JWT for this specific call
result = await client.api4("Contact", "get", params, token=user_jwt)
```

This works with CiviCRM's `authx` extension (bundled since 5.36), which accepts both API keys and JWTs via the `Authorization: Bearer` header. The token is never logged in audit output.

All convenience methods (`get`, `create`, `update`, `delete`, `save`, `replace`, `get_fields`, `get_actions`) accept the `token` keyword argument.

### Error Recovery

Multi-step workflow tools use rollback semantics to prevent orphaned records:

- **Event registration with payment** (`civicrm_register_for_event`): If contribution or payment link creation fails after the participant is created, the participant is automatically deleted. Cleanup failures are reported in the error message so orphaned records can be identified.
- **Contributions with notes** (`civicrm_record_contribution`): If note creation fails, the contribution is still returned with a warning — the note failure doesn't hide the successfully created contribution.
- All validation (e.g., missing `contribution_amount`) runs before any API mutations.

## Architecture

```
src/everything_civi/
├── server.py            # FastMCP setup, lifespan, tool allowlist
├── config.py            # Pydantic settings with env var binding
├── client.py            # Async REST client with retry, rate limiting, audit logging
├── logging_config.py    # Structured JSON log formatter
├── crud_tools.py        # 6 generic CRUD tools
├── discovery_tools.py   # 5 schema introspection tools
├── workflow_tools.py    # 9 domain-specific workflow tools
├── searchkit_tools.py   # 3 SearchKit tools
├── utility_tools.py     # 3 bulk operation tools
├── admin_tools.py       # 2 admin/health tools
├── prompts.py           # 3 MCP prompts
└── resources.py         # 3 MCP resources
```

The server uses a layered architecture:

1. **Core CRUD** — Generic tools that work with any CiviCRM entity via the uniform APIv4 pattern
2. **Discovery** — Schema introspection so the AI can learn entity structures at runtime
3. **Workflows** — Multi-step operations that chain API calls with name resolution and validation
4. **SearchKit** — Execute pre-built saved searches
5. **Utility** — Pagination, bulk import, and smart contact matching
6. **Admin** — Health monitoring and cache management

All tools communicate through a single async REST client with:
- Bearer token authentication (static API key or per-request JWT)
- Form-encoded parameter passing (CiviCRM REST API requirement)
- Retry with exponential backoff for transient errors
- Semaphore-based rate limiting
- Structured JSON audit logging with PII redaction
- Tool permission allowlist for access control
- Rollback semantics for multi-step operations
- Lazy initialization to avoid event loop issues

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
.venv/bin/pytest tests/ -v

# Run integration tests (requires live CiviCRM)
CIVICRM_BASE_URL=https://your-site.org CIVICRM_API_KEY=your-key \
  .venv/bin/pytest tests/test_integration*.py -v

# Lint
.venv/bin/ruff check src/ tests/
```

## License

MIT
