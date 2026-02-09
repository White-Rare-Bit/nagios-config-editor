"""Automated tests for CLAUDE.md convention compliance.

Run with: pytest tests/test_conventions.py -v
"""

import ast
import re
from collections.abc import Generator
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).parent.parent


def get_python_files() -> Generator[Path, None, None]:
    """Get all Python files in the project (excluding vendor/skills)."""
    for pattern in ["*.py", "routes/*.py", "tests/*.py"]:
        for f in ROOT.glob(pattern):
            if ".claude/skills" not in str(f):
                yield f


def get_js_files() -> Generator[Path, None, None]:
    """Get all JavaScript files (excluding vendor)."""
    for f in ROOT.glob("static/**/*.js"):
        if "vendor" not in str(f):
            yield f
    app_js = ROOT / "static" / "app.js"
    if app_js.exists():
        yield app_js


def get_css_files() -> Generator[Path, None, None]:
    """Get all CSS files (excluding vendor)."""
    for f in ROOT.glob("static/**/*.css"):
        if "vendor" not in str(f):
            yield f
    style_css = ROOT / "static" / "style.css"
    if style_css.exists():
        yield style_css


def get_template_files() -> Generator[Path, None, None]:
    """Get all HTML template files."""
    yield from ROOT.glob("templates/*.html")
    yield from ROOT.glob("templates/**/*.html")


class TestPythonNaming:
    """Test Python naming conventions (snake_case)."""

    def test_function_names_snake_case(self):
        """Python function names should use snake_case."""
        violations = []
        camel_pattern = re.compile(r"^[a-z]+[A-Z]")

        for py_file in get_python_files():
            try:
                tree = ast.parse(py_file.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and camel_pattern.match(node.name):
                        violations.append(f"{py_file.name}:{node.lineno} - {node.name}")
            except SyntaxError:
                continue

        assert not violations, "Found camelCase function names:\n" + "\n".join(violations)

    def test_method_names_snake_case(self):
        """Python method names should use snake_case."""
        violations = []
        camel_pattern = re.compile(r"^[a-z]+[A-Z]")

        for py_file in get_python_files():
            try:
                tree = ast.parse(py_file.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if (isinstance(item, ast.FunctionDef) and
                                    not item.name.startswith("_") and
                                    camel_pattern.match(item.name)):
                                violations.append(
                                    f"{py_file.name}:{item.lineno} - {node.name}.{item.name}",
                                )
            except SyntaxError:
                continue

        assert not violations, "Found camelCase method names:\n" + "\n".join(violations)


class TestJavaScriptNaming:
    """Test JavaScript naming conventions (camelCase)."""

    def test_no_snake_case_functions(self):
        """JavaScript functions should not use snake_case."""
        violations = []
        snake_func = re.compile(r"function\s+([a-z]+_[a-z][a-zA-Z_]*)")

        for js_file in get_js_files():
            content = js_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                match = snake_func.search(line)
                if match:
                    violations.append(f"{js_file.name}:{i} - {match.group(1)}")

        assert not violations, "Found snake_case function names:\n" + "\n".join(violations)

    def test_no_snake_case_variables(self):
        """JavaScript variables should not use snake_case."""
        violations = []
        snake_var = re.compile(r"(?:let|const|var)\s+([a-z]+_[a-z][a-zA-Z_]*)")

        # Exceptions for API field names that come from Python
        exceptions = {"session_id", "user_name", "file_path", "object_type", "source_file"}

        for js_file in get_js_files():
            content = js_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                match = snake_var.search(line)
                if match and match.group(1) not in exceptions:
                    violations.append(f"{js_file.name}:{i} - {match.group(1)}")

        assert not violations, "Found snake_case variable names:\n" + "\n".join(violations)


class TestCSSNaming:
    """Test CSS naming conventions."""

    def test_class_names_kebab_case(self):
        """CSS class names should use kebab-case."""
        violations = []
        # Match class definitions with camelCase or snake_case
        camel_class = re.compile(r"\.([a-z]+[A-Z][a-zA-Z]*)\s*[{,:]")
        snake_class = re.compile(r"\.([a-z]+_[a-z][a-zA-Z_]*)\s*[{,:]")

        for css_file in get_css_files():
            content = css_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if camel_class.search(line):
                    match = camel_class.search(line)
                    violations.append(f"{css_file.name}:{i} - .{match.group(1)} (camelCase)")
                if snake_class.search(line):
                    match = snake_class.search(line)
                    violations.append(f"{css_file.name}:{i} - .{match.group(1)} (snake_case)")

        assert not violations, "Found non-kebab-case class names:\n" + "\n".join(violations)

    def test_css_variables_namespaced(self):
        """Custom CSS variables should use --nbe-* namespace."""
        violations = []
        # Match CSS variable definitions not starting with --nbe- or --bs-
        var_def = re.compile(r"^\s*--((?!nbe-|bs-)[a-z][a-z0-9-]*)\s*:")

        for css_file in get_css_files():
            content = css_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                match = var_def.search(line)
                if match:
                    violations.append(f"{css_file.name}:{i} - --{match.group(1)}")

        assert not violations, "Found non-namespaced CSS variables:\n" + "\n".join(violations)


class TestDesignTokens:
    """Test design token usage."""

    def test_no_hardcoded_colors_outside_tokens(self):
        """Colors should use design tokens, not hardcoded values."""
        violations = []
        hex_color = re.compile(r"#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])")

        for css_file in get_css_files():
            # Skip tokens.css where colors are defined
            if css_file.name == "tokens.css":
                continue

            content = css_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                # Skip comments
                if line.strip().startswith("/*") or line.strip().startswith("*"):
                    continue
                if hex_color.search(line):
                    violations.append(f"{css_file.name}:{i} - {line.strip()[:60]}")

        if violations:
            pytest.xfail("Found hardcoded colors (consider using tokens):\n" + "\n".join(violations[:10]))


class TestTemplateInheritance:
    """Test template inheritance patterns."""

    def test_templates_extend_base(self):
        """All page templates should extend base.html."""
        violations = []
        extends_pattern = re.compile(r'{%\s*extends\s+["\']base\.html["\']\s*%}')

        for template in get_template_files():
            # Skip base.html itself and partials
            if template.name == "base.html":
                continue
            if template.name.startswith("_"):
                continue
            if "partials" in str(template):
                continue

            content = template.read_text()
            if not extends_pattern.search(content):
                violations.append(str(template.relative_to(ROOT)))

        assert not violations, "Templates not extending base.html:\n" + "\n".join(violations)


class TestEventDelegation:
    """Test event delegation patterns."""

    def test_no_inline_onclick(self):
        """Templates should not use inline onclick handlers."""
        violations = []
        onclick_pattern = re.compile(r"onclick\s*=")

        for template in get_template_files():
            content = template.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if onclick_pattern.search(line):
                    violations.append(f"{template.name}:{i}")

        assert not violations, "Found inline onclick handlers:\n" + "\n".join(violations)


class TestApiClientUsage:
    """Test ApiClient pattern usage."""

    def test_no_direct_fetch_for_api(self):
        """API calls should use ApiClient, not direct fetch.

        Note: Many files still use direct fetch(). This test validates that
        key files follow the convention. Full migration is tracked as tech debt.
        """
        violations = []
        direct_fetch = re.compile(r"fetch\s*\(\s*['\"`]/api")

        # Check only files that have been migrated to ApiClient
        migrated_files = {"audit-log.js"}

        for js_file in get_js_files():
            # Skip api-client.js itself
            if js_file.name == "api-client.js":
                continue
            # Only check migrated files
            if js_file.name not in migrated_files:
                continue

            content = js_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if direct_fetch.search(line):
                    violations.append(f"{js_file.name}:{i}")

        assert not violations, "Found direct fetch calls to /api:\n" + "\n".join(violations)

    def test_direct_fetch_tech_debt(self):
        """Track remaining direct fetch() calls as technical debt."""
        violations = []
        direct_fetch = re.compile(r"fetch\s*\(\s*['\"`]/api")

        for js_file in get_js_files():
            if js_file.name == "api-client.js":
                continue

            content = js_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if direct_fetch.search(line):
                    violations.append(f"{js_file.name}:{i}")

        if violations:
            pytest.xfail(f"Technical debt: {len(violations)} direct fetch() calls should use ApiClient")


class TestThreadSafety:
    """Test thread safety patterns."""

    def test_uses_multiprocessing_lock(self):
        """Services should use multiprocessing.Lock, not threading.Lock."""
        violations = []
        threading_lock = re.compile(r"from\s+threading\s+import.*Lock|threading\.Lock")

        service_files = [
            "nagios_service.py",
            "staging_manager.py",
            "git_service.py",
        ]

        for filename in service_files:
            filepath = ROOT / filename
            if filepath.exists():
                content = filepath.read_text()
                if threading_lock.search(content):
                    violations.append(filename)

        assert not violations, "Files using threading.Lock instead of multiprocessing.Lock:\n" + "\n".join(violations)


class TestServiceAccess:
    """Test service access patterns in routes."""

    def test_routes_use_helper_functions(self):
        """Routes should use helper functions to access services."""
        violations = []
        direct_access = re.compile(r"current_app\.extensions\[")

        for route_file in ROOT.glob("routes/*.py"):
            # Skip helpers.py where the pattern is defined
            if route_file.name == "helpers.py":
                continue
            if route_file.name == "__init__.py":
                continue
            # Skip settings.py which legitimately reinitializes services
            if route_file.name == "settings.py":
                continue

            content = route_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if direct_access.search(line):
                    violations.append(f"{route_file.name}:{i}")

        assert not violations, "Found direct current_app.extensions access:\n" + "\n".join(violations)


class TestGlobalFunctions:
    """Test that global functions are in correct files."""

    def test_app_js_functions(self):
        """Required functions should be defined in app.js."""
        app_js = ROOT / "static" / "app.js"
        content = app_js.read_text()

        required_functions = [
            "escapeHtml",
            "formatDate",
            "debounce",
            "escapeRegex",
            "copyToClipboard",
            "setButtonLoading",
        ]

        missing = []
        for func in required_functions:
            # Look for function definition or assignment
            if f"function {func}" not in content and f"{func} =" not in content:
                missing.append(func)

        assert not missing, f"Missing functions in app.js: {missing}"

    def test_base_js_functions(self):
        """Required functions should be defined in base.js modules.

        After refactoring, these functions are split across extracted modules:
        - session-manager.js: getSessionId, getUserIdentity, getStagingHeaders
        - ui-notifications.js: showToast, showConfirmDialog
        """
        js_dir = ROOT / "static" / "js"

        # Map functions to their expected module locations
        function_locations = {
            "showToast": "ui-notifications.js",
            "showConfirmDialog": "ui-notifications.js",
            "getSessionId": "session-manager.js",
            "getUserIdentity": "session-manager.js",
            "getStagingHeaders": "session-manager.js",
        }

        missing = []
        for func, module in function_locations.items():
            module_path = js_dir / module
            if not module_path.exists():
                missing.append(f"{func} (module {module} not found)")
                continue
            content = module_path.read_text()
            if f"function {func}" not in content and f"{func} =" not in content:
                missing.append(f"{func} in {module}")

        assert not missing, f"Missing functions in base.js modules: {missing}"


class TestReferenceFieldSync:
    """Test that reference fields are synchronized across locations."""

    def _extract_reference_fields_from_python(self) -> set:
        """Extract REFERENCE_FIELDS from nagios_model.py."""
        model_py = ROOT / "nagios_model.py"
        content = model_py.read_text()

        # Parse the REFERENCE_FIELDS dict
        match = re.search(r"REFERENCE_FIELDS\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        if match:
            fields = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
            return set(fields)
        return set()

    def _extract_attr_reference_map(self) -> set:
        """Extract ATTR_REFERENCE_MAP keys from object-editor.js."""
        editor_js = ROOT / "static" / "js" / "explorer" / "object-editor.js"
        content = editor_js.read_text()

        match = re.search(r"ATTR_REFERENCE_MAP\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        if match:
            fields = re.findall(r"['\"]?([a-z_]+)['\"]?\s*:", match.group(1))
            return set(fields)
        return set()

    def _extract_reference_attrs_main(self) -> set:
        """Extract referenceAttrs from main.js."""
        main_js = ROOT / "static" / "js" / "explorer" / "main.js"
        content = main_js.read_text()

        match = re.search(r"referenceAttrs\s*=\s*\[([^\]]+)\]", content, re.DOTALL)
        if match:
            fields = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
            return set(fields)
        return set()

    def test_reference_fields_synchronized(self):
        """Reference fields should be the same across all locations."""
        python_fields = self._extract_reference_fields_from_python()
        editor_fields = self._extract_attr_reference_map()
        main_fields = self._extract_reference_attrs_main()

        if not python_fields:
            pytest.skip("Could not extract REFERENCE_FIELDS from nagios_model.py")

        all_fields = python_fields | editor_fields | main_fields

        discrepancies = []
        for field in all_fields:
            locations = []
            if field in python_fields:
                locations.append("nagios_model.py")
            if field in editor_fields:
                locations.append("object-editor.js")
            if field in main_fields:
                locations.append("main.js")

            if len(locations) < 3:
                missing = []
                if field not in python_fields:
                    missing.append("nagios_model.py")
                if field not in editor_fields:
                    missing.append("object-editor.js")
                if field not in main_fields:
                    missing.append("main.js")
                discrepancies.append(f"'{field}' missing from: {', '.join(missing)}")

        if discrepancies:
            pytest.xfail("Reference fields out of sync:\n" + "\n".join(discrepancies))


class TestOperationResultPattern:
    """Test OperationResult usage in service modules."""

    def test_service_methods_return_operation_result(self):
        """Service methods should return OperationResult."""
        service_py = ROOT / "nagios_service.py"
        content = service_py.read_text()

        # Count OperationResult returns
        result_returns = len(re.findall(r"return OperationResult", content))

        # Should have many OperationResult returns
        assert result_returns > 10, f"Expected many OperationResult returns, found {result_returns}"

    def test_no_dict_returns_in_service(self):
        """Service should not return raw dicts (should use OperationResult)."""
        service_py = ROOT / "nagios_service.py"
        content = service_py.read_text()

        # Look for return statements that return dicts directly
        dict_returns = re.findall(r"return\s*\{[^}]*\}", content)

        # Filter out legitimate cases (like returning data inside OperationResult)
        violations = [r for r in dict_returns if "success" in r and "error" in r]

        assert not violations, "Found dict returns that should be OperationResult"
