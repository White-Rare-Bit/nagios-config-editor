# Nagios Bulk Editor

I've been working with Nagios Core for a few years now, and have noticed over time that Nagios configuration can become very "organic" (barnacled with technical debt) this is a project that aims to help Nagios Core administrators a safe and modern way to edit their Nagios configuration in bulk without resorting to grepping and reading through a ton of text files. 

There are a multitude of safety features implemented to prevent unrecoverable situations.

Staging -> arguably the most important, changes are written to a json staging file and do not impact files on disk prior to committing in the commit menu.

Backups -> Prior to applying the configuration a zip of the entire configuration directory is taken.

Git integration -> Serves a couple of purposes in the application, attribution for the audit log, changes are tracked by git in addition to full backups.

Nagios verification -> The option to run verify against the Nagios configuration after committing

Staging lock -> polling checks that staging doesn't currently doesn't have any content and will produce a lock banner for users in other sessions if staging content is detected.

Audit log -> Changes are tracked under the git username set in the settings per session.

Full disclosure, this has been completely written with the assistance of Claude Code, all due respect to Anthropic and it's team for producing this incredible tool.
