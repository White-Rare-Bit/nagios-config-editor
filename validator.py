"""
Nagios Configuration Validator

Validates Nagios configuration by calling the nagios binary
and parsing the output for errors and warnings.
"""

import subprocess
import re
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from nagios_model import OperationResult


@dataclass
class ValidationResult:
    """Result of a Nagios configuration validation."""
    success: bool
    errors: List[Dict]
    warnings: List[Dict]
    total_errors: int
    total_warnings: int
    raw_output: str

    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'errors': self.errors,
            'warnings': self.warnings,
            'total_errors': self.total_errors,
            'total_warnings': self.total_warnings,
            'raw_output': self.raw_output
        }


class NagiosValidator:
    """Validates Nagios configuration files."""

    # Pattern to match Nagios version output
    # Examples: "Nagios Core 4.4.6", "Nagios 3.5.1", "Naemon Core 1.2.3"
    NAGIOS_VERSION_PATTERN = re.compile(
        r'(Nagios(\s+Core)?|Naemon(\s+Core)?)\s+\d+\.\d+',
        re.IGNORECASE
    )

    def __init__(self, nagios_bin: str = "/usr/local/nagios/bin/nagios",
                 config_file: str = "./sample-config/nagios.cfg"):
        self.nagios_bin = nagios_bin
        self.config_file = config_file

        # Try common Nagios binary locations
        if not os.path.exists(self.nagios_bin):
            common_paths = [
                "/usr/sbin/nagios",
                "/usr/bin/nagios",
                "/usr/local/bin/nagios",
                "/opt/nagios/bin/nagios"
            ]
            for path in common_paths:
                if os.path.exists(path):
                    self.nagios_bin = path
                    break

    def _create_error_result(self, message: str, raw_output: str = None) -> ValidationResult:
        """Create a standard error ValidationResult with a single error message."""
        return ValidationResult(
            success=False,
            errors=[{'message': message}],
            warnings=[],
            total_errors=1,
            total_warnings=0,
            raw_output=raw_output or message
        )

    def validate(self, skip_binary_verification: bool = False) -> ValidationResult:
        """
        Run nagios -v to validate the configuration.

        Args:
            skip_binary_verification: Skip verification that binary is Nagios.
                                     Only set True if binary was already verified.

        Returns a ValidationResult with parsed errors and warnings.
        """
        # Security: Verify binary is actually Nagios before executing with config
        if not skip_binary_verification:
            result = self.verify_binary()
            if not result.success:
                return self._create_error_result(
                    f'Invalid Nagios binary: {result.error}',
                    f'Binary verification failed: {result.error}'
                )

        if not os.path.exists(self.nagios_bin):
            return self._create_error_result(
                f'Nagios binary not found at {self.nagios_bin}',
                f'Nagios binary not found. Searched: {self.nagios_bin}'
            )

        if not os.path.exists(self.config_file):
            return self._create_error_result(
                f'Config file not found at {self.config_file}',
                f'Configuration file not found: {self.config_file}'
            )

        try:
            result = subprocess.run(
                [self.nagios_bin, '-v', self.config_file],
                capture_output=True,
                text=True,
                timeout=60
            )
            output = result.stdout + result.stderr
            return self._parse_output(output, result.returncode == 0)
        except subprocess.TimeoutExpired:
            return self._create_error_result(
                'Validation timed out after 60 seconds',
                'Timeout: Nagios validation took too long'
            )
        except Exception as e:
            return self._create_error_result(
                f'Failed to run validation: {str(e)}',
                str(e)
            )

    def _parse_output(self, output: str, exit_success: bool) -> ValidationResult:
        """Parse nagios -v output to extract errors and warnings.

        D-03: Nagios output format compatibility notes:
        - Tested with Nagios Core 4.x output format (4.0.0 - 4.5.x)
        - Error patterns match both legacy "Error:" and newer "CONFIG ERROR:" prefixes
        - File/line extraction pattern handles Nagios 4.x format: "Error in file 'X' on line N:"
        - Nagios 3.x used slightly different output; may need pattern updates if 3.x support needed
        - Naemon and Icinga use similar formats but not explicitly tested
        """
        errors = []
        warnings = []

        # Pattern for error lines (compatible with Nagios Core 4.x)
        error_patterns = [
            r"Error:\s*(.+)",
            r"CONFIG ERROR:\s*(.+)",
            r"Error in file '([^']+)' on line (\d+):\s*(.+)",
        ]

        # Pattern for warning lines (compatible with Nagios Core 4.x)
        warning_patterns = [
            r"Warning:\s*(.+)",
            r"CONFIG WARNING:\s*(.+)",
        ]

        lines = output.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()

            # Check for errors
            for pattern in error_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 3:
                        errors.append({
                            'file': match.group(1),
                            'line': int(match.group(2)),
                            'message': match.group(3)
                        })
                    else:
                        errors.append({
                            'message': match.group(1),
                            'raw_line': line
                        })
                    break

            # Check for warnings
            for pattern in warning_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    warnings.append({
                        'message': match.group(1),
                        'raw_line': line
                    })
                    break

        # Extract totals from summary line
        total_errors = len(errors)
        total_warnings = len(warnings)

        # Look for summary line like "Total Errors: 0"
        error_count_match = re.search(r'Total Errors:\s*(\d+)', output)
        if error_count_match:
            total_errors = max(total_errors, int(error_count_match.group(1)))

        warning_count_match = re.search(r'Total Warnings:\s*(\d+)', output)
        if warning_count_match:
            total_warnings = max(total_warnings, int(warning_count_match.group(1)))

        # Determine success
        success = exit_success and total_errors == 0

        return ValidationResult(
            success=success,
            errors=errors,
            warnings=warnings,
            total_errors=total_errors,
            total_warnings=total_warnings,
            raw_output=output
        )

    def check_binary_exists(self) -> Tuple[bool, str]:
        """Check if the Nagios binary exists and is executable."""
        if os.path.exists(self.nagios_bin):
            if os.access(self.nagios_bin, os.X_OK):
                return True, self.nagios_bin
            return False, f"Nagios binary exists but is not executable: {self.nagios_bin}"
        return False, f"Nagios binary not found: {self.nagios_bin}"

    def verify_binary(self) -> OperationResult:
        """Verify that the binary is actually a Nagios executable.

        Security: Prevents command injection by verifying the binary
        produces expected Nagios version output before using it.

        Returns:
            OperationResult with data containing version string on success
        """
        if not os.path.exists(self.nagios_bin):
            return OperationResult(success=False, error=f"Binary not found: {self.nagios_bin}")

        if not os.access(self.nagios_bin, os.X_OK):
            return OperationResult(success=False, error=f"Binary is not executable: {self.nagios_bin}")

        try:
            # Run with -V flag to get version info
            result = subprocess.run(
                [self.nagios_bin, '-V'],
                capture_output=True,
                text=True,
                timeout=5  # Short timeout for version check
            )
            output = result.stdout + result.stderr

            # Check if output matches expected Nagios/Naemon version pattern
            match = self.NAGIOS_VERSION_PATTERN.search(output)
            if match:
                # Extract full version line for display
                version_line = None
                for line in output.split('\n'):
                    if self.NAGIOS_VERSION_PATTERN.search(line):
                        version_line = line.strip()
                        break
                return OperationResult(success=True, data=version_line)

            # Binary exists and runs but doesn't produce expected output
            return OperationResult(success=False, error="Binary does not appear to be Nagios (unexpected version output)")

        except subprocess.TimeoutExpired:
            return OperationResult(success=False, error="Binary timed out when checking version")
        except PermissionError:
            return OperationResult(success=False, error=f"Permission denied executing: {self.nagios_bin}")
        except Exception as e:
            return OperationResult(success=False, error=f"Error verifying binary: {str(e)}")


def validate_config(nagios_bin: str = "/usr/local/nagios/bin/nagios",
                    config_file: str = "./sample-config/nagios.cfg") -> ValidationResult:
    """Convenience function to validate Nagios configuration."""
    validator = NagiosValidator(nagios_bin, config_file)
    return validator.validate()


def verify_nagios_binary(binary_path: str) -> OperationResult:
    """Verify that a path points to a valid Nagios binary.

    Security: Use this to validate user-provided paths before saving
    to configuration. Prevents command injection attacks where a malicious
    path could execute arbitrary code during validation.

    Args:
        binary_path: Path to the binary to verify

    Returns:
        OperationResult with data containing version string on success

    Example:
        result = verify_nagios_binary('/usr/sbin/nagios')
        if not result.success:
            return jsonify({'error': result.error}), 400
    """
    validator = NagiosValidator(nagios_bin=binary_path)
    return validator.verify_binary()
