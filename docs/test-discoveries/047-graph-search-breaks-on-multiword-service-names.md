# Bug 047: Graph Search Breaks for Multi-Word Service Queries

## Severity
**Major**

## Summary
Searching for a service by its compound display name (e.g. "HTTP on web-servers") returns "No matches found" even when the exact service exists. Only single-word prefix searches work. An admin cannot type a service's natural Nagios name into the search box.

## Steps to Reproduce
1. Navigate to Graph View
2. Type "HTTP on web" in the search box

**Expected:** "HTTP on web-servers" service appears in results
**Actual:** "No matches found"

3. Delete back to "HTTP"

**Expected (and actual):** "HTTP on web-servers" now appears

## Additional Observations
- "HTTP on web-s" → no matches
- "HTTP on" → no matches
- "HTTP" → matches (shows "HTTP on web-servers", "HTTPS on web-servers", etc.)

The search appears to break as soon as the query includes the word "on" followed by any additional characters. Services in Nagios are naturally identified as "description on host/hostgroup", so this renders the search nearly useless for services.

## Impact
Admins cannot search services by their standard Nagios display name. With dozens of services all sharing descriptions like "PING", "HTTP", "Memory Usage", an admin must search by bare description and visually scan the list — with no indication of which hostgroup/host each result belongs to in the dropdown.
