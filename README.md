# Nagios Bulk Editor

A safe, modern web UI for bulk-editing Nagios Core configurations.

https://github.com/user-attachments/assets/cba01855-61b0-4721-9dee-b63d79f255d8

I've been working with Nagios Core for a few years now and have noticed that configurations tend to become very "organic" over time, i.e. barnacled with technical debt. This project gives Nagios administrators a way to edit their configuration in bulk without resorting to grepping through a ton of text files.

## Features

### Object Explorer
Browse, create, edit, delete, and move Nagios objects across configuration files. Supports all major object types — hosts, services, contacts, commands, timeperiods, dependencies, escalations, and more. Drag-and-drop between files, bulk operations, tabbed editing, and autocomplete for reference fields.

### Analysis
- **Dependency graphs** — visualize host, service, and escalation relationships
- **Inheritance trees** — trace template chains and see resolved attributes
- **Health checks** — detect orphaned references, missing fields, duplicates, unused templates, broken escalation chains
- **Smart grouping** — suggests template consolidation when objects share common attributes
- **Impact analysis** — see what breaks before you delete something

### Safety

- **Staging**: Changes are written to a shadow copy and do not touch files on disk until you explicitly apply them in the commit menu.
- **Undo**: File-level snapshots before every mutation, with multi-step undo.
- **Backups**: A zip of the entire configuration directory is taken before every apply.
- **Git integration**: Changes are tracked by git in addition to full backups, with attribution tied to the audit log.
- **Nagios verification**: Option to run `nagios -v` against the configuration after applying.
- **Staging lock**: Polling checks detect active staging content and display a lock banner for other sessions.
- **Conflict detection**: Detects if files were modified externally while you were editing.
- **Audit log**: All changes are tracked under the git username set in settings per session.

### Built-in Documentation
Nagios object reference for all object types with attribute descriptions, required fields, and inheritance rules.

## Getting Started

### Prerequisites

- Python 3.10+
- Git (optional — for version control features)
- Nagios binary (optional — for `nagios -v` validation)

### Installation

```bash
git clone https://github.com/White-Rare-Bit/nagios-config-editor.git
cd nagios-config-editor
pip install -r requirements.txt
python3 app.py
```

Then open [http://localhost:8080](http://localhost:8080).

### Configuration

On first launch, go to **Settings** and point the editor at your `nagios.cfg`. It discovers all `cfg_dir` and `cfg_file` entries automatically.

Settings are stored in `config/settings.json`. Environment variables override file settings:

| Variable | Description |
|----------|-------------|
| `NAGIOS_CFG` | Path to nagios.cfg |
| `NAGIOS_BIN` | Path to nagios binary |
| `BACKUP_PATH` | Backup storage directory |

### Workflow

1. Open the **Explorer** — your configuration objects appear in the left tree
2. Click an object to view/edit its attributes in the right pane
3. Make changes — they're staged, not written to your live config
4. Review changes in the **diff view**
5. **Apply** to write to disk, or **Discard** to throw them away
6. Optionally **commit** via git for version history

## Production Deployment

For running on a production Linux host alongside Nagios (systemd + Gunicorn + Apache), see [deploy/README.md](deploy/README.md).

## Contributing

```bash
python3 -m pytest tests/ -v   # run tests
python3 app.py                 # run locally
```

The `sample-config/` directory contains a test Nagios configuration for local development.

Dependencies: `flask` and `gunicorn` (see `requirements.txt`)

## License

[MIT](LICENSE)

---

This project was built entirely with the assistance of [Claude Code](https://claude.ai/code). All due respect to Anthropic and its team for producing this incredible tool.
