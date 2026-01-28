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

    def validate(self) -> ValidationResult:
        """
        Run nagios -v to validate the configuration.

        Returns a ValidationResult with parsed errors and warnings.
        """
        if not os.path.exists(self.nagios_bin):
            return ValidationResult(
                success=False,
                errors=[{'message': f'Nagios binary not found at {self.nagios_bin}'}],
                warnings=[],
                total_errors=1,
                total_warnings=0,
                raw_output=f'Nagios binary not found. Searched: {self.nagios_bin}'
            )

        if not os.path.exists(self.config_file):
            return ValidationResult(
                success=False,
                errors=[{'message': f'Config file not found at {self.config_file}'}],
                warnings=[],
                total_errors=1,
                total_warnings=0,
                raw_output=f'Configuration file not found: {self.config_file}'
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
            return ValidationResult(
                success=False,
                errors=[{'message': 'Validation timed out after 60 seconds'}],
                warnings=[],
                total_errors=1,
                total_warnings=0,
                raw_output='Timeout: Nagios validation took too long'
            )
        except Exception as e:
            return ValidationResult(
                success=False,
                errors=[{'message': f'Failed to run validation: {str(e)}'}],
                warnings=[],
                total_errors=1,
                total_warnings=0,
                raw_output=str(e)
            )

    def _parse_output(self, output: str, exit_success: bool) -> ValidationResult:
        """Parse nagios -v output to extract errors and warnings."""
        errors = []
        warnings = []

        # Pattern for error lines
        error_patterns = [
            r"Error:\s*(.+)",
            r"CONFIG ERROR:\s*(.+)",
            r"Error in file '([^']+)' on line (\d+):\s*(.+)",
        ]

        # Pattern for warning lines
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


def validate_config(nagios_bin: str = "/usr/local/nagios/bin/nagios",
                    config_file: str = "./sample-config/nagios.cfg") -> ValidationResult:
    """Convenience function to validate Nagios configuration."""
    validator = NagiosValidator(nagios_bin, config_file)
    return validator.validate()
