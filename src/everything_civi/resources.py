from mcp.server.fastmcp import FastMCP


QUERYING_GUIDE = """\
# CiviCRM APIv4 Query Construction Guide

## WHERE Clause Operators

Every WHERE clause is a list of conditions: `[field, operator, value]`.

| Operator | Meaning | Example |
|---|---|---|
| `=` | Equals | `["status_id", "=", 1]` |
| `!=` | Not equals | `["contact_type", "!=", "Organization"]` |
| `>` | Greater than | `["total_amount", ">", 100]` |
| `>=` | Greater than or equal | `["receive_date", ">=", "2024-01-01"]` |
| `<` | Less than | `["total_amount", "<", 500]` |
| `<=` | Less than or equal | `["end_date", "<=", "2024-12-31"]` |
| `LIKE` | SQL LIKE (use `%` wildcard) | `["display_name", "LIKE", "Smith%"]` |
| `NOT LIKE` | Negated LIKE | `["email", "NOT LIKE", "%example.com"]` |
| `IN` | Value in list | `["status_id", "IN", [1, 2, 3]]` |
| `NOT IN` | Value not in list | `["contact_type", "NOT IN", ["Household"]]` |
| `BETWEEN` | Between two values (inclusive) | `["total_amount", "BETWEEN", [100, 500]]` |
| `NOT BETWEEN` | Outside range | `["age", "NOT BETWEEN", [18, 65]]` |
| `IS NULL` | Field is null | `["deceased_date", "IS NULL"]` (no value) |
| `IS NOT NULL` | Field is not null | `["email", "IS NOT NULL"]` |
| `IS EMPTY` | Null or empty string | `["nick_name", "IS EMPTY"]` |
| `IS NOT EMPTY` | Not null and not empty string | `["first_name", "IS NOT EMPTY"]` |
| `CONTAINS` | Array/serialised field contains value | `["group", "CONTAINS", 5]` |
| `NOT CONTAINS` | Array does not contain value | `["tag", "NOT CONTAINS", 3]` |
| `REGEXP` | Regular expression match | `["display_name", "REGEXP", "^(John|Jane)"]` |
| `NOT REGEXP` | Negated regexp | `["email", "NOT REGEXP", "test"]` |

### Compound conditions

Use `"OR"` to group disjunctions:

```json
{
  "where": [
    ["contact_type", "=", "Individual"],
    ["OR", [
      ["first_name", "=", "Alice"],
      ["first_name", "=", "Bob"]
    ]]
  ]
}
```

## Pseudoconstant Suffix Syntax

Many fields that store numeric IDs have pseudoconstant suffixes that let you
filter or select by human-readable values instead of raw IDs.

| Suffix | Returns | Example field |
|---|---|---|
| `:name` | Machine name (stable across environments) | `contribution_status_id:name` |
| `:label` | Localised display label | `activity_type_id:label` |
| `:description` | Option description | `gender_id:description` |
| `:icon` | Icon CSS class | `activity_type_id:icon` |
| `:color` | Colour hex code | `case_status_id:color` |

**Usage in WHERE:**
```json
{"where": [["contribution_status_id:name", "=", "Completed"]]}
```

**Usage in SELECT:**
```json
{"select": ["id", "total_amount", "contribution_status_id:label"]}
```

Always prefer `:name` over raw numeric IDs for portability.

## Implicit Joins (Dot Notation)

When a field has a foreign key (`fk_entity`), you can traverse the relationship
with dot notation to select or filter on the related entity's fields.

```json
{
  "select": ["id", "total_amount", "contact_id.display_name", "contact_id.email_primary.email"],
  "where": [["contact_id.contact_type", "=", "Individual"]]
}
```

You can chain multiple levels: `contact_id.employer_id.display_name`.

## Explicit Joins

Use the `join` parameter for more complex relationships or when you need
LEFT/INNER/EXCLUDE join behaviour.

```json
{
  "select": ["id", "display_name", "a.email"],
  "join": [
    ["Email AS a", "LEFT", null, ["a.contact_id", "=", "id"], ["a.is_primary", "=", true]]
  ]
}
```

**Join syntax:** `["EntityName AS alias", "JOIN_TYPE", bridge_or_null, ...on_clauses]`

Join types:
- `"INNER"` -- only rows with a match
- `"LEFT"` -- all rows, NULL for non-matches
- `"EXCLUDE"` -- only rows *without* a match

### Bridge Entity Joins

For many-to-many relationships (e.g., Contact-to-Group via GroupContact):

```json
{
  "select": ["id", "display_name", "g.title"],
  "join": [
    ["Group AS g", "LEFT", "GroupContact"]
  ]
}
```

When the third element is a string (the bridge entity name) instead of an
on-clause array, CiviCRM automatically resolves the bridge.

## Aggregation Functions

Available aggregate functions for use in `select`:

| Function | Example |
|---|---|
| `COUNT:` | `"COUNT:id"` |
| `SUM:` | `"SUM:total_amount"` |
| `AVG:` | `"AVG:total_amount"` |
| `MIN:` | `"MIN:receive_date"` |
| `MAX:` | `"MAX:receive_date"` |
| `GROUP_CONCAT:` | `"GROUP_CONCAT:email"` |

### groupBy and having

```json
{
  "select": ["contact_id", "contact_id.display_name", "SUM:total_amount"],
  "where": [["receive_date", ">=", "2024-01-01"]],
  "groupBy": ["contact_id"],
  "having": [["SUM:total_amount", ">", 1000]]
}
```

## ORDER BY and LIMIT

```json
{
  "orderBy": {"total_amount": "DESC", "receive_date": "ASC"},
  "limit": 25,
  "offset": 0
}
```

## Common Patterns

### Count records without fetching them
```json
{"select": ["row_count"], "limit": 0}
```

### Check if any records exist
```json
{"select": ["id"], "limit": 1}
```

### Select with row count included
Set `"select": ["row_count", "id", ...]` to include a total count alongside
the returned rows.

### Gotchas

1. **`IS NULL` and `IS EMPTY` take no value argument.** Write
   `["field", "IS NULL"]`, not `["field", "IS NULL", ""]`.
2. **Pseudoconstant suffixes in WHERE use the option's name/label, not the
   ID.** `["status_id:name", "=", "Completed"]`, not
   `["status_id:name", "=", 1]`.
3. **Dot-notation joins only work on fields with `fk_entity` set.** Use
   `civicrm_describe_entity` to check which fields support this.
4. **`BETWEEN` expects exactly a two-element list.**
5. **`orderBy` is an object (dict), not a list.** Keys are field names, values
   are `"ASC"` or `"DESC"`.
6. **`groupBy` is a flat list of field names, not nested arrays.**
7. **`having` filters run after aggregation.** Reference the alias used in
   `select`, not the raw expression.
8. **`limit: 0` means "no rows returned"** (useful with `row_count`).  Omit
   `limit` entirely or set a positive value to get rows.
"""

ENTITIES_GUIDE = """\
# CiviCRM Entity Relationship Overview

## Core Domains

### Contacts
The foundation of CiviCRM.  Almost every other entity references a Contact.

| Entity | Purpose |
|---|---|
| **Contact** | Individuals, Organizations, or Households |
| **Email** | Email addresses (multiple per contact) |
| **Phone** | Phone numbers |
| **Address** | Postal addresses |
| **Website** | URLs |
| **IM** | Instant-messaging handles |
| **Relationship** | Typed link between two contacts (employer/employee, parent/child, etc.) |
| **RelationshipType** | Defines available relationship types |
| **Group** | Static or smart groups of contacts |
| **GroupContact** | Bridge: Contact membership in a Group |
| **Tag** | Hierarchical labels for contacts (and other entities) |
| **EntityTag** | Bridge: Tag applied to a Contact (or Activity, Case, etc.) |
| **Note** | Free-text notes attached to contacts or other entities |

### Contributions (Fundraising / Payments)
Financial transactions and related records.

| Entity | Purpose |
|---|---|
| **Contribution** | A financial transaction (donation, fee, payment) |
| **ContributionRecur** | Recurring-contribution schedule |
| **ContributionSoft** | Soft credit linking a contribution to another contact |
| **FinancialType** | Classification of revenue (Donation, Event Fee, etc.) |
| **FinancialTrxn** | Underlying double-entry financial transaction |
| **LineItem** | Line-item detail within a contribution |
| **Payment** | Payment applied against a contribution balance |
| **PriceSet** | Collection of price fields for events/memberships |
| **PriceField** | Single configurable price field |
| **PriceFieldValue** | Option within a price field |

### Events
Event management, registration, and attendance.

| Entity | Purpose |
|---|---|
| **Event** | A scheduled event (conference, workshop, etc.) |
| **Participant** | A contact's registration for an event |
| **ParticipantStatusType** | Possible statuses (Registered, Attended, Cancelled, etc.) |
| **LocBlock** | Location block linking address, email, phone to an event |

### Memberships
Membership tracking and renewal.

| Entity | Purpose |
|---|---|
| **Membership** | A contact's membership record |
| **MembershipType** | Defines a membership tier / category |
| **MembershipStatus** | Membership lifecycle statuses (New, Current, Expired, etc.) |
| **MembershipPayment** | Bridge: links a Membership to a Contribution |

### Cases
Case management for tracking multi-step workflows.

| Entity | Purpose |
|---|---|
| **Case** | A case record (service request, application, etc.) |
| **CaseType** | Defines case types and their timelines |
| **CaseContact** | Bridge: contacts involved in a case |
| **CaseActivity** | Bridge: activities associated with a case |

### Activities
Activity tracking across all domains.

| Entity | Purpose |
|---|---|
| **Activity** | A scheduled or completed action (meeting, call, email, etc.) |
| **ActivityContact** | Bridge: contacts involved in an activity (assignee, target, source) |
| **ActivityType** | (via OptionValue) Defines types of activities |

### Mailings
Bulk email and mailing list management.

| Entity | Purpose |
|---|---|
| **Mailing** | A bulk mailing |
| **MailingGroup** | Groups included/excluded from a mailing |
| **MailingJob** | Delivery job for a mailing |
| **MailingEventQueue** | Recipient queue entries |
| **MailingEventDelivered** | Successful delivery events |
| **MailingEventBounce** | Bounce events |
| **MailingEventOpened** | Open-tracking events |
| **MailingEventTrackableURLOpen** | Click-tracking events |
| **MailingEventUnsubscribe** | Unsubscribe events |

### Campaigns
Campaign tracking for organising activities, contributions, and events.

| Entity | Purpose |
|---|---|
| **Campaign** | A campaign (advocacy, fundraising, etc.) |
| **Survey** | A survey or petition tied to a campaign |

### Pledges
Pledged future payments.

| Entity | Purpose |
|---|---|
| **Pledge** | A promise to pay over time |
| **PledgePayment** | Individual scheduled payments within a pledge |

### Grants
Grant management.

| Entity | Purpose |
|---|---|
| **Grant** | A grant application or award |

## Key Relationships

```
Contact ──< Email, Phone, Address, Website, IM
Contact ──< Contribution ──< LineItem, Payment, FinancialTrxn
Contact ──< Participant >── Event
Contact ──< Membership >── MembershipType
Contact ──< CaseContact >── Case ──< CaseActivity >── Activity
Contact ──< ActivityContact >── Activity
Contact ──< GroupContact >── Group
Contact ──< EntityTag >── Tag
Contact ──< Relationship >── Contact
Contribution ──< ContributionSoft
Contribution >── FinancialType
ContributionRecur ──< Contribution
Membership ──< MembershipPayment >── Contribution
Event ──< Participant
Campaign ──< Contribution, Activity, Event
Pledge ──< PledgePayment >── Contribution
```

Legend: `──<` = one-to-many, `>──` = many-to-one

## Common Workflows

### Record a donation
1. Find or create a **Contact**
2. Create a **Contribution** linked to the contact with appropriate **FinancialType**

### Register for an event
1. Find or create a **Contact**
2. Find the **Event**
3. Create a **Participant** linking the contact to the event
4. Optionally create a **Contribution** for the registration fee

### Create a membership
1. Find or create a **Contact**
2. Choose a **MembershipType**
3. Create a **Membership** for the contact
4. Create a **Contribution** and link via **MembershipPayment**

### Log an activity
1. Create an **Activity** with the appropriate type
2. Link contacts via **ActivityContact** with record_type_id:
   - Source (who performed it)
   - Assignee (who is assigned)
   - Target (who it's about)

### Open a case
1. Find or create a **Contact**
2. Choose a **CaseType**
3. Create a **Case**
4. Link the contact via **CaseContact**
5. Activities within the case are tracked via **CaseActivity**
"""


def register_resources(mcp: FastMCP, client) -> None:

    @mcp.resource("civicrm://guide/querying")
    async def querying_guide() -> str:
        """Comprehensive reference for constructing CiviCRM APIv4 queries.

        Covers WHERE operators, pseudoconstant syntax, implicit and explicit
        joins, bridge entities, aggregation, groupBy/having, ordering, limits,
        and common patterns with gotchas.
        """
        return QUERYING_GUIDE

    @mcp.resource("civicrm://guide/entities")
    async def entities_guide() -> str:
        """Overview of CiviCRM's core entity domains and how they relate.

        Describes Contacts, Contributions, Events, Memberships, Cases,
        Activities, Mailings, Campaigns, Pledges, and Grants -- the key
        entities in each domain, their relationships, and common workflows.
        """
        return ENTITIES_GUIDE

    @mcp.resource("civicrm://entities")
    async def live_entity_list() -> str:
        """Live list of all entities available on the connected CiviCRM instance.

        Dynamically fetched from the API -- includes entities added by
        extensions that may not appear in the static guide.
        """
        try:
            result = await client.api4(
                "Entity",
                "get",
                {
                    "select": ["name", "title", "description", "type"],
                    "orderBy": {"name": "ASC"},
                },
            )
        except Exception as exc:
            return f"# Error fetching entities\n\nCould not connect to CiviCRM: {exc}"

        entities = result.get("values", result)
        lines = []
        for e in entities:
            title = e.get("title", "")
            desc = e.get("description", "")
            etype = e.get("type", "")
            suffix = f" ({etype})" if etype else ""
            detail = f" -- {desc}" if desc else ""
            lines.append(f"- **{e['name']}**: {title}{suffix}{detail}")
        return "# Entities on This CiviCRM Instance\n\n" + "\n".join(lines)
