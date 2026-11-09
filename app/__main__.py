"""Allow running with python3 -m app."""
from . import create_app

if __name__ == "__main__":
    app = create_app()
    print("Nagios Bulk Editor")  # noqa: T201
    print(f"Config path: {app.extensions['service'].config_path or './sample-config'}")  # noqa: T201
    print("Starting server on http://localhost:8080")  # noqa: T201
    app.run(debug=True, host="127.0.0.1", port=8080)
