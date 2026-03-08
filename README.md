# Nagios Bulk Editor

A safe, modern web UI for bulk-editing Nagios Core configurations.

<video src="https://github.com/White-Rare-Bit/nagios-config-editor/releases/download/demo-assets/Nagios_Bulk_Editor.mp4" controls width="100%"></video>

I've been working with Nagios Core for a few years now and have noticed that configurations tend to become very "organic" over time, i.e. barnacled with technical debt. This project gives Nagios administrators a way to edit their configuration in bulk without resorting to grepping through a ton of text files.

## Safety Features

- **Staging**: Changes are written to a staging file and do not touch files on disk until you explicitly apply them in the commit menu.
- **Backups**: A zip of the entire configuration directory is taken before every apply.
- **Git integration**: Changes are tracked by git in addition to full backups, with attribution tied to the audit log.
- **Nagios verification**: Option to run `nagios -v` against the configuration after applying.
- **Staging lock**: Polling checks detect active staging content and display a lock banner for other sessions.
- **Audit log**: All changes are tracked under the git username set in settings per session.

## Getting Started

```bash
pip install -r requirements.txt
python3 app.py
```

Then open [http://localhost:8080](http://localhost:8080).

## License

[MIT](LICENSE)

---

This project was built entirely with the assistance of [Claude Code](https://claude.ai/claude-code). All due respect to Anthropic and its team for producing this incredible tool.
