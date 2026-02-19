# Bug 051: "Network" Quick View Applied to Object Types Where It Is Meaningless

## Severity
**Minor** (cosmetic/UX — all quick views are already broken by Bug 044)

## Summary
The "Network" quick view button appears for `serviceescalation`, `hostescalation`, `servicegroup`, and `hostdependency` object types. "Network" is defined as "Host parent-child topology and service bindings" — a concept that has no meaning for escalation objects or service groups.

## Quick View Matrix (observed)

| Object Type | Quick Views Offered |
|---|---|
| host | Inheritance, Network, Notifications, Services, Monitoring, Escalations, Dependencies, Full Graph |
| service | Inheritance, Network, Notifications, Monitoring, Escalations, Dependencies, Full Graph |
| hostgroup | Inheritance, Notifications, Services, Members, Escalations, Dependencies, Full Graph |
| contact | Inheritance, Notified By, Full Graph |
| contactgroup | Inheritance, Members, Notified By, Full Graph |
| command | Used By, Full Graph |
| timeperiod | Used By, Full Graph |
| servicegroup | Inheritance, **Network**, Notifications, Members, Escalations, Dependencies, Full Graph |
| servicedependency | Inheritance, **Network**, Monitoring, Full Graph |
| serviceescalation | Inheritance, Notifications, **Network**, Full Graph |
| hostescalation | Inheritance, Notifications, **Network**, Full Graph |
| hostdependency | Inheritance, **Network**, Monitoring, Full Graph |

## Analysis per Misapplied Type

- **serviceescalation + hostescalation + "Network"**: An escalation defines notification levels. Network topology (parent-child hosts) is irrelevant. A more useful view would be "Escalation Chain" — show the host/service it targets, the contact groups at each level, and the time range.

- **servicegroup + "Network"**: A servicegroup is a logical label. It has no network topology. "Members" + "Notified By" would be the useful views.

- **hostdependency + "Network"**: This one could be argued — host dependencies ARE network topology. But the label "Network" is misleading here; "Topology" or "Dependency Chain" would be clearer.

## Additional Design Observations

**Missing quick views that would be genuinely useful:**
- `servicedependency`: A "Dependency Chain" view showing master service → dependent service → what triggers failure would be the highest-value view
- `serviceescalation`: An "Escalation Path" view showing service → escalation level 1 (contacts) → level 2 (contacts) timeline
- `contact`: "What Notifies Me" showing all services/hosts this person receives alerts for (requires reverse traversal — see Bug 050)
