"""Tests for docs page API endpoint."""

import pytest


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

    @pytest.mark.parametrize("page", ["../base", "../docs", "..\\base", "overview.html", "Overview"])
    def test_traversal_and_malformed_names_return_404(self, app, page):
        """Called directly, because routing rejects '/' before the view would run:
        GET /api/docs/../base never reaches docs_page at all."""
        from werkzeug.exceptions import NotFound
        from app.routes.pages import docs_page
        with app.test_request_context(), pytest.raises(NotFound):
            docs_page(page)

    def test_response_is_html_fragment(self, client):
        """Response is an HTML fragment, not a full page."""
        resp = client.get("/api/docs/overview")
        html = resp.data.decode()
        assert "<!DOCTYPE" not in html
        assert "<html" not in html
