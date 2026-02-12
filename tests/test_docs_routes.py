"""Tests for docs page API endpoint."""


class TestDocsRoute:
    """Test GET /api/docs/<page> endpoint."""

    def test_valid_page_returns_html(self, client):
        """Fetching a valid doc page returns 200 with HTML content."""
        resp = client.get("/api/docs/overview")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")

    def test_invalid_page_returns_404(self, client):
        """Fetching a nonexistent doc page returns 404."""
        resp = client.get("/api/docs/nonexistent-page")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        """Path traversal attempts are rejected."""
        resp = client.get("/api/docs/../base")
        # Flask normalizes this, but verify it doesn't serve base.html
        assert resp.status_code == 404

    def test_response_is_html_fragment(self, client):
        """Response is an HTML fragment, not a full page."""
        resp = client.get("/api/docs/overview")
        html = resp.data.decode()
        assert "<!DOCTYPE" not in html
        assert "<html" not in html
