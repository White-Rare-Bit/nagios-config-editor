# Production Deployment

Deploy the Nagios Bulk Editor on a Linux host alongside Nagios.

## Prerequisites

- Python 3.10+
- Nagios Core installed and working
- Apache with `mod_proxy` (optional -- for reverse proxying)
- Git (optional -- for the app's version control features)

## Quick Start

**1. Clone the repository**

```bash
sudo git clone https://github.com/YOUR_ORG/nagios-bulk-editor.git /opt/nagios-bulk-editor
sudo chown -R nagios:nagios /opt/nagios-bulk-editor
```

**2. Create a virtualenv and install dependencies**

```bash
cd /opt/nagios-bulk-editor
sudo -u nagios python3 -m venv venv
sudo -u nagios venv/bin/pip install -r requirements.txt
```

**3. Configure**

```bash
sudo -u nagios cp deploy/settings.json.example config/settings.json
```

Edit `config/settings.json` and set paths to match your Nagios installation (see [Configuration](#configuration) below).

**4. Run Gunicorn manually to verify**

```bash
sudo -u nagios venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 wsgi:app
```

**5. Open `http://<host>:8080` in a browser to confirm it works.**

### Workers

Running several Gunicorn workers (`-w 2` or more) is supported. Workers share
nothing in memory: the staging session, its lock, undo history and the saved
settings all live on disk, and file locks keep workers from interleaving
writes. Two things follow from that:

- All workers must run on the same host and see the same filesystem (the
  `.shadow` directory in particular). Do not put workers on different machines.
- Restarting or recycling a worker does not discard staged changes. A staging
  session ends only on Apply/Commit, Discard, or a lock break.

## Configuration

### config/settings.json

| Field | Description | Typical path |
|-------|-------------|-------------|
| `nagios_cfg` | Main Nagios config file | `/usr/local/nagios/etc/nagios.cfg` |
| `nagios_bin` | Nagios binary (used for config validation) | `/usr/local/nagios/bin/nagios` or `/usr/sbin/nagios` |
| `resource_cfg` | Nagios resource file | `/usr/local/nagios/etc/resource.cfg` |
| `primary_dir` | Directory containing your `.cfg` object files | `/usr/local/nagios/etc` |

### Environment variable overrides

| Variable | Overrides |
|----------|-----------|
| `NAGIOS_CFG` | `paths.nagios_cfg` |
| `NAGIOS_BIN` | `paths.nagios_bin` |
| `FLASK_SECRET_KEY` | Flask session signing key |

Environment variables take precedence over `config/settings.json`.

Generate a secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Running as a systemd Service

**1. Copy the unit file**

```bash
sudo cp deploy/nagios-bulk-editor.service.example /etc/systemd/system/nagios-bulk-editor.service
```

**2. Edit the unit file**

Set `FLASK_SECRET_KEY` to a random value (see command above). Adjust `NAGIOS_CFG` and `NAGIOS_BIN` if your paths differ from the defaults.

**3. Enable and start**

```bash
sudo systemctl daemon-reload
sudo systemctl enable nagios-bulk-editor
sudo systemctl start nagios-bulk-editor
```

**4. Verify**

```bash
sudo systemctl status nagios-bulk-editor
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/
```

## Apache Reverse Proxy (Optional)

**1. Copy the config**

```bash
sudo cp deploy/apache.conf.example /etc/apache2/conf-available/nagios-bulk-editor.conf
```

**2. Edit the config**

Uncomment the basic auth section if you want password protection. Adjust the `AuthUserFile` path to match your Nagios htpasswd file.

If you enable basic auth, also uncomment the `RequestHeader set X-Remote-User` line, and `NBE_TRUSTED_USER_HEADER=X-Remote-User` in the systemd unit. The audit log then records the logged-in user. Without it, the audit log records the name and email each browser was given on the Identity tab, which anyone can set to anything. With the variable set, requests that arrive without the header are logged as `unverified: <claimed identity>`. Only set it when Gunicorn is reachable solely through Apache, which is the case with the provided `--bind 127.0.0.1:8080`.

**3. Enable modules and config**

```bash
sudo a2enmod proxy proxy_http headers
sudo a2enconf nagios-bulk-editor
sudo systemctl reload apache2
```

The editor is now available at `http://<host>/editor/`.

## Logs

| Location | Contents |
|----------|----------|
| `logs/app.log` | Operational logs (errors, warnings, info) |
| `logs/audit.log` | Who changed what and when |

Both rotate at `max_file_size_mb` and keep `max_backup_files` old copies (`app.log.1`, ...). Rotation is coordinated between Gunicorn workers through `<logfile>.lock` files, so no external logrotate is needed. The log viewer and its download include the rotated files. Timestamps are ISO 8601 with UTC offset. The audit log cannot be cleared from the app.

Under systemd, Gunicorn access and error logs go to the journal:

```bash
journalctl -u nagios-bulk-editor -f
```

## Updating

```bash
cd /opt/nagios-bulk-editor
sudo -u nagios git pull
sudo -u nagios venv/bin/pip install -r requirements.txt
sudo systemctl restart nagios-bulk-editor
```
