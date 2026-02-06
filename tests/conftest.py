"""Shared test fixtures for Nagios Bulk Editor tests."""

import os
import pytest
from pathlib import Path
from app import create_app


@pytest.fixture
def sample_config_path():
    """Path to the sample-config directory shipped with the repo."""
    path = os.path.join(os.path.dirname(__file__), '..', 'sample-config')
    path = os.path.abspath(path)
    assert os.path.isdir(path), f"sample-config not found at {path}"
    return path


@pytest.fixture
def app(sample_config_path):
    """Create Flask app pointed at the sample-config directory."""
    application = create_app(config_path=sample_config_path)
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def service(app):
    """NagiosService instance from the app."""
    with app.app_context():
        yield app.extensions['service']
