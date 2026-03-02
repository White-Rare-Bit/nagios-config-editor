# Candidate Migration Commandments

All plans in this directory MUST comply with these directives.

---

1. **No live config mutation until Apply.** Nothing shall be written to the live Nagios configuration until the user clicks Apply in the commit menu. The only operation before Apply is copying the config to a candidate directory.

2. **UI visual parity.** The user interface must stay as visually similar as possible to the current system while migrating to the new candidate methodology. No gratuitous UI changes.

3. **Full audit logging.** All operations must be logged through both the audit logging system (audit_service.py) and the application logging system.

4. **Proper error handling everywhere.** All errors must have proper error handling — no silent failures, no swallowed exceptions.

5. **Dead code deletion.** Any functionality that has zero use in the new candidate system must be deleted, not left behind.

6. **Full functionality migration.** Any functionality that still has use in the new system must be properly migrated — nothing dropped on the floor.

7. **Palo Alto candidate model.** The candidate configuration system must be based on the Palo Alto Networks methodology: copy config to candidate, edit candidate, apply candidate to live.

8. **Change tracking document.** A listing of all changes made must be maintained and ticked off as completed so that nothing is missed.

9. **Complete planning before implementation.** The entire system must be fully planned before any code changes begin.

10. **Linting enforcement.** All code must pass ESLint (JavaScript) and Ruff (Python) before committing. No dirty commits.

11. **Playwright validation.** Playwright tests must be used where it makes sense to validate UI changes gradually, ensuring each migrated part works as expected.
