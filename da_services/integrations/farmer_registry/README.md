# Farmer Registry Integration

This module provides integration with the Farmer Registry (OpenG2P-based) service.

## Configuration

### Mock Backend (Development)

Default configuration - uses hardcoded test data, no network calls.

```json
{
  "farmer_registry_backend": "mock"
}
```

### HTTP Backend (Production)

Connect to real Farmer Registry service with configurable routes.

**File:** `sites/da-services.localhost/site_config.json`

```json
{
  "farmer_registry_backend": "http",
  "farmer_registry_url": "http://farmer-registry:8080",
  "farmer_registry_api_key": "your-secret-api-key",
  "farmer_registry_api_version": "v1",
  "farmer_registry_timeout": 30,
  
  "farmer_registry_endpoints": {
    "get_farmer": "/api/{version}/registry/farmer/{farmer_id}",
    "list_farmers": "/api/{version}/registry/farmer",
    "get_plots": "/api/{version}/registry/land",
    "update_farmer": "/api/{version}/registry/farmer/{farmer_id}"
  }
}
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `farmer_registry_backend` | string | `"mock"` | Backend type: `"mock"` or `"http"` |
| `farmer_registry_url` | string | `"http://farmer-registry:8080"` | Base URL of Farmer Registry API |
| `farmer_registry_api_key` | string | `null` | API key for authentication (Bearer token) |
| `farmer_registry_api_version` | string | `"v1"` | API version (replaces `{version}` in endpoint templates) |
| `farmer_registry_timeout` | int | `30` | HTTP request timeout in seconds |
| `farmer_registry_endpoints` | object | See defaults | Configurable endpoint path templates |

## Endpoint Templates

Endpoint templates support placeholders:
- `{version}` - Replaced with `farmer_registry_api_version`
- `{farmer_id}` - Replaced with actual farmer ID
- Other parameters as needed

### Default Endpoints

```python
{
    "get_farmer": "/api/{version}/registry/farmer/{farmer_id}",
    "list_farmers": "/api/{version}/registry/farmer",
    "get_plots": "/api/{version}/registry/land",
    "update_farmer": "/api/{version}/registry/farmer/{farmer_id}"
}
```

## Environment-Specific Configuration

### Development
```json
{
  "farmer_registry_backend": "mock"
}
```

### Staging
```json
{
  "farmer_registry_backend": "http",
  "farmer_registry_url": "https://staging-farmer-registry.example.com",
  "farmer_registry_api_key": "staging-api-key"
}
```

### Production
```json
{
  "farmer_registry_backend": "http",
  "farmer_registry_url": "https://farmer-registry.production.com",
  "farmer_registry_api_key": "production-api-key"
}
```

## API Version Migration

When Farmer Registry upgrades from v1 to v2:

**Before (v1):**
```json
{
  "farmer_registry_api_version": "v1"
}
```

**After (v2) - Just change config:**
```json
{
  "farmer_registry_api_version": "v2"
}
```

All API calls automatically update:
- `/api/v1/registry/farmer/123` → `/api/v2/registry/farmer/123`

## Route Migration

If Farmer Registry changes route structure:

**Old routes:**
```
/api/v1/registry/farmer/{id}
/api/v1/registry/land
```

**New routes:**
```
/api/v2/farmers/{id}
/api/v2/plots
```

**Update config (no code changes!):**
```json
{
  "farmer_registry_api_version": "v2",
  "farmer_registry_endpoints": {
    "get_farmer": "/api/{version}/farmers/{farmer_id}",
    "list_farmers": "/api/{version}/farmers",
    "get_plots": "/api/{version}/plots",
    "update_farmer": "/api/{version}/farmers/{farmer_id}"
  }
}
```

## Usage in Code

```python
from da_services.integrations.farmer_registry import get_farmer_registry_client

# Get client (automatically uses config to choose mock or http)
client = get_farmer_registry_client()

# Get farmer
farmer = client.get_farmer("farmer-uuid-001")

# List farmers
farmers, total = client.list_farmers(woreda="ET04-W01", limit=50)

# Get plots
plots = client.get_farmer_plots("farmer-uuid-001")

# Update farmer
updated = client.update_farmer("farmer-uuid-001", {"phone": "912345678"})
```

## Testing

Tests always use mock backend regardless of configuration:

```python
# In tests, this always returns MockFarmerRegistryClient
client = get_farmer_registry_client()
```

## Troubleshooting

### Connection Errors
```python
# Check configuration
frappe.conf.get("farmer_registry_url")
frappe.conf.get("farmer_registry_backend")

# Test connection
import requests
response = requests.get(f"{base_url}/health")
```

### Authentication Errors
```python
# Verify API key
frappe.conf.get("farmer_registry_api_key")

# Check headers
client = get_farmer_registry_client()
print(client.headers)
```

### Route Errors
```python
# Verify endpoint configuration
client = get_farmer_registry_client()
print(client.endpoints)

# Test URL building
url = client._build_url("get_farmer", farmer_id="test-123")
print(url)
```

## Error Logging

All HTTP errors are logged to Frappe's error log:

```python
# View recent errors
frappe.get_all("Error Log", 
    filters={"error": ["like", "%Farmer Registry%"]},
    fields=["creation", "error"],
    order_by="creation desc",
    limit=10
)
```
