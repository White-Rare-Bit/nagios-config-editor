"""Allow running with python3 -m app."""
from . import app, get_config_path

if __name__ == "__main__":
    print("Nagios Bulk Editor")  # noqa: T201
    print(f"Config path: {get_config_path()}")  # noqa: T201
    print("Starting server on http://localhost:8080")  # noqa: T201
    app.run(debug=True, host="127.0.0.1", port=8080)
