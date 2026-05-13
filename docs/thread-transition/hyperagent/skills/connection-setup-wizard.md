# Skill: connection-setup-wizard

| | |
|---|---|
| **ID** | `unknown` |
| **Description** | HyperApp wizard for data warehouse connection setup |
| **Tags** | — |
| **When to use** | — |

---

# Connection Setup Wizard

When the user wants to connect to a data warehouse or integration (Databricks, Snowflake, BigQuery, Postgres, etc.), use CreateHyperApp to generate an interactive setup wizard.

## When to Use

- User says "connect to Databricks", "set up Snowflake", "configure my data warehouse"
- User asks about connection settings or credentials for a supported integration
- User wants to test or manage their connection settings

## Step 1: Discover Available Integrations

First, fetch the list of registered integrations and their field schemas:

```
GET /api/settings/connections
```

Response:
```json
{
  "integrations": [
    {
      "id": "databricks",
      "name": "Databricks",
      "description": "SQL warehouse querying and data analysis",
      "icon": "🧱",
      "category": "data_warehouse",
      "configured": false,
      "fields": [
        { "key": "host", "label": "Workspace Host", "type": "text", "required": true, "placeholder": "dbc-abc123.cloud.databricks.com" },
        { "key": "warehouseId", "label": "SQL Warehouse ID", "type": "text", "required": true },
        { "key": "authMode", "label": "Authentication Method", "type": "select", "required": true, "defaultValue": "token", "options": [...] },
        { "key": "token", "label": "Personal Access Token", "type": "password", "required": false, "requiredWhen": { "field": "authMode", "value": "token" } },
        ...
      ]
    }
  ]
}
```

## Step 2: Create the HyperApp

Use CreateHyperApp to build a setup form for the requested integration. **The field schema from the API tells you exactly what form fields to render** — you don't need to hardcode field definitions.

The HyperApp should:

1. **Load existing settings** on mount: `GET /api/settings/connections/{integrationId}`
2. **Render form fields dynamically** from the field schema:
   - `type: "text"` → text input
   - `type: "password"` → password input (with show/hide toggle)
   - `type: "select"` → dropdown from `options` array
   - `requiredWhen` → conditionally show/require field based on another field's value
3. **Test Connection** button: `POST /api/settings/connections/{integrationId}/test` with form values
4. **Save** button: `POST /api/settings/connections/{integrationId}` to persist settings

## API Endpoints (for any integration ID)

### GET /api/settings/connections/{id}
Returns current settings with secrets masked:
```json
{
  "configured": true,
  "fields": { "host": "adb-123.net", "warehouseId": "abc", "authMode": "token", "token": null, "clientId": null, "clientSecret": null },
  "masked": { "masked_token": "dapi****wxyz", "has_token": "true", "masked_clientSecret": null, "has_clientSecret": "false" }
}
```

### POST /api/settings/connections/{id}/test
Tests connection with inline credentials. Request body is a flat object of field keys→values:
```json
{ "host": "adb-123.net", "warehouseId": "abc", "authMode": "token", "token": "dapi..." }
```
Response: `{ "success": true, "message": "Connected successfully", "latencyMs": 234 }`

### POST /api/settings/connections/{id}
Saves settings. Same body shape. Secret fields are only updated if new values are provided.

### DELETE /api/settings/connections/{id}
Removes all settings for the integration.

## HyperApp Implementation Notes

- Use `fetch()` for all API calls (relative URLs)
- Show loading states during API calls
- Show clear success/error feedback after test and save
- Pre-populate form fields from GET response on mount
- For masked secrets, show placeholder indicating a secret is saved
- Only send secret fields if the user entered a new value
- Make the form visually polished — trust your aesthetic judgment

