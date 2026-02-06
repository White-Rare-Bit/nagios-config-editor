"""Tests for inheritance chain API with multi-template use."""

import pytest
import tempfile
import shutil
from pathlib import Path
from app import create_app


@pytest.fixture
def app():
    """Create Flask app with multi-template config."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / 'nagios'
    test_config_path.mkdir()

    (test_config_path / 'templates.cfg').write_text('''
define host {
    name                    base-host
    register                0
    max_check_attempts      5
    notification_interval   30
}

define host {
    name                    linux-host
    register                0
    check_command           check-host-alive
    notification_period     24x7
}

define host {
    name                    multi-parent-host
    register                0
    use                     base-host,linux-host
    contact_groups          admins
}
''')

    (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       web-01
    alias           Web Server 01
    address         10.0.0.1
    use             base-host,linux-host
}

define host {
    host_name       single-template-host
    alias           Single Template Host
    address         10.0.0.2
    use             base-host
}
''')

    app = create_app(config_path=str(test_config_path))
    app.config['TESTING'] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


class TestInheritanceChainMultiTemplate:
    """Test that inheritance chain API handles comma-separated use values."""

    def test_single_template_chain(self, client):
        """Single template use works correctly."""
        resp = client.get('/api/inheritance/host/single-template-host')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['depth'] == 2  # object + 1 template
        names = [item.get('attributes', {}).get('host_name') or item.get('attributes', {}).get('name')
                 for item in data['chain']]
        assert 'single-template-host' in names[0]
        assert 'base-host' in names[1]

    def test_multi_template_chain(self, client):
        """Comma-separated use resolves both templates."""
        resp = client.get('/api/inheritance/host/web-01')
        assert resp.status_code == 200
        data = resp.get_json()
        # Should have: web-01 + base-host + linux-host = depth 3
        assert data['depth'] >= 3
        template_names = []
        for item in data['chain']:
            attrs = item.get('attributes', {})
            template_names.append(attrs.get('name') or attrs.get('host_name'))
        assert 'base-host' in template_names
        assert 'linux-host' in template_names

    def test_multi_template_chain_via_template(self, client):
        """Template with multi-template use is also resolved."""
        resp = client.get('/api/inheritance/host/multi-parent-host')
        assert resp.status_code == 200
        data = resp.get_json()
        template_names = []
        for item in data['chain']:
            attrs = item.get('attributes', {})
            template_names.append(attrs.get('name') or attrs.get('host_name'))
        assert 'base-host' in template_names
        assert 'linux-host' in template_names
