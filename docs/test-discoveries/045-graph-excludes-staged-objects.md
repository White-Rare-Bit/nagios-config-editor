# Bug 045: Dependency Graph Excludes Staged (Uncommitted) Objects

## Severity
**Minor**

## Summary
The `/api/dependencies` endpoint returns only committed (on-disk) objects. Objects created, renamed, or moved in staging are invisible in the Graph View until committed. An admin creating a new host in staging cannot verify its template inheritance or service relationships in the graph before committing.

## Steps to Reproduce
1. In the Explorer, create a new host with `use: linux-server`
2. Do NOT commit — leave in staging
3. Navigate to Graph View
4. Search for the new host name

Expected: Host appears in search and can be added to graph, showing its template link to `linux-server`
Actual: Host not found in search — graph data is 213 nodes (committed state only)

## Technical Detail
`/api/dependencies` returns `{"nodes": [...213 items...], "edges": [...765 items...]}` with no staging session header applied. The endpoint does not merge staging creations/edits into the graph data.

## Impact
Low for most workflows (commit first, then verify), but an admin doing pre-commit review of complex cross-object relationships cannot use the graph as a preview tool. The staging commit dialog's diff is the only pre-commit reference.

## Note
This may be by design given the complexity of computing staged graph edges. Worth considering whether the graph API should accept a staging session parameter to include pending changes.
