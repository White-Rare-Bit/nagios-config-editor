# Bug 052: Escalation and Dependency Objects Use Non-Typeable Characters in Search Identity

## Severity
**Minor**

## Summary
`servicedependency` and some `serviceescalation` nodes are identified internally using the `→` arrow character (e.g., `servicedependency:Apache Status→HTTP`). This character cannot be typed in the search box, making these objects undiscoverable via search. An admin cannot directly navigate to a servicedependency in the graph.

## Evidence
```js
window._graphDebug.allNodes.filter(n => n.type === 'servicedependency').map(n => n.id)
// Returns:
// "servicedependency:MySQL→MySQL Slave Status"
// "servicedependency:Apache Status→HTTP"
// "servicedependency:HTTP→Application Health Check"
// "servicedependency:HTTPS→HTTPS Certificate"
```

The `→` character is U+2192 (RIGHTWARDS ARROW) — not on a standard keyboard.

## Steps to Reproduce
1. Navigate to Graph View
2. Type "Apache Status" in search box
3. Observe: returns "Apache Status on web-servers" (service), not the dependency

There is no search query that reaches the `servicedependency:Apache Status→HTTP` node.

## Expected Behavior
Servicedependencies should be findable by searching either:
- The master service name ("Apache Status")
- The dependent service name ("HTTP")
- Or use a human-readable format like "Apache Status depends on HTTP"

## Impact
Admins cannot directly add a servicedependency to the graph by searching. They can only find them by expanding from connected service/host nodes (which also doesn't work due to Bug 044). Dependency objects are effectively inaccessible as graph starting points.
