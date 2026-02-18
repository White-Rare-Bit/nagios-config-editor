# 022 — No Pre-Creation Duplicate Name Validation

**Phase:** 7 — Error Handling
**Severity:** Major
**Category:** Validation / Data Integrity

## Steps to Reproduce

1. Open the Object Explorer
2. Click "+" on `hosts.cfg` to create a new host
3. In the "Enter name..." breadcrumb field, type an existing host name: `web-prod-01`
4. Tab away / attempt to save
5. Observe: no duplicate warning is shown, the object is staged

Alternatively, via API:

```bash
curl -X POST http://localhost:8080/api/staging \
  -H 'X-Session-Id: <session>' \
  -H 'Content-Type: application/json' \
  -d '{ "stagedCreations": [{"object_type":"host","target_file":"sample-config/hosts.cfg","attributes":{"host_name":"web-prod-01","address":"1.2.3.4"}}] }'
```

## Actual Behavior

The system silently stages an object with a name that already exists in the config. No inline warning, no toast, no rejection.

Duplicates are only surfaced post-hoc via the **Suggestions / Issues** analysis panel after the object is already staged — they are never prevented at creation time.

## Expected Behavior

When the user types a name that already exists for the same object type, the Create Object form should show an inline validation error (e.g., "A host named 'web-prod-01' already exists") and prevent staging until the user picks a unique name.

## Notes

- The Suggestions panel does correctly flag duplicates via the analysis engine (`analysis.js`) after the fact
- The duplicate is also visible in the tree with a warning icon once staged
- But the user could easily miss this and proceed to commit a config with duplicate definitions, which causes a Nagios validation failure at apply time
- This contrasts with the service duplicate check (discovery #009) which checks `host_name + service_description` — that check also appears to be post-hoc
