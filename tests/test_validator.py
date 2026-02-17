"""Tests for validator module — output parsing and binary verification."""

import os
import stat
import subprocess
from unittest.mock import patch

import pytest

from validator import NagiosValidator


class TestParseOutput:
    """Unit tests for NagiosValidator._parse_output (pure function)."""

    def setup_method(self):
        self.v = NagiosValidator()

    def test_clean_output(self):
        output = (
            "Nagios Core 4.4.6\n"
            "Total Warnings: 0\n"
            "Total Errors:   0\n"
            "Things look okay - No serious problems were detected\n"
        )
        result = self.v._parse_output(output, exit_success=True)
        assert result.success is True
        assert result.total_errors == 0
        assert result.total_warnings == 0

    def test_single_error(self):
        output = (
            "Error: Could not find host 'web-99'\n"
            "Total Warnings: 0\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False
        assert result.total_errors == 1
        assert "web-99" in result.errors[0]["message"]

    def test_error_with_file_and_line(self):
        output = (
            "Error in file '/etc/nagios/hosts.cfg' on line 42: "
            "Could not find host 'missing-host'\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 1
        assert result.errors[0]["file"] == "/etc/nagios/hosts.cfg"
        assert result.errors[0]["line"] == 42

    def test_config_error_prefix(self):
        output = "CONFIG ERROR: Invalid directive 'foo'\nTotal Errors: 1\n"
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 1

    def test_warnings(self):
        output = (
            "Warning: Host 'web-01' has no services\n"
            "Warning: Unused command 'old-check'\n"
            "Total Warnings: 2\n"
            "Total Errors:   0\n"
        )
        result = self.v._parse_output(output, exit_success=True)
        assert result.success is True
        assert result.total_warnings == 2
        assert len(result.warnings) == 2

    def test_mixed_errors_and_warnings(self):
        output = (
            "Warning: Something minor\n"
            "Error: Something critical\n"
            "Total Warnings: 1\n"
            "Total Errors:   1\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False
        assert result.total_errors == 1
        assert result.total_warnings == 1

    def test_summary_line_overrides_counted(self):
        # If summary says 3 errors but we only parsed 1, use max
        output = (
            "Error: One detected error\n"
            "Total Errors:   3\n"
        )
        result = self.v._parse_output(output, exit_success=False)
        assert result.total_errors == 3

    def test_exit_failure_with_zero_parsed_errors(self):
        # Exit code failed but no parseable errors — still not success
        output = "Some unexpected output\nTotal Errors: 0\n"
        result = self.v._parse_output(output, exit_success=False)
        assert result.success is False


class TestCheckBinaryExists:
    """Tests for NagiosValidator.check_binary_exists."""

    def test_nonexistent_binary(self, tmp_path):
        v = NagiosValidator(nagios_bin=str(tmp_path / "nonexistent"))
        exists, msg = v.check_binary_exists()
        assert exists is False
        assert "not found" in msg

    def test_existing_non_executable(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("not a real binary")
        binary.chmod(stat.S_IRUSR)
        v = NagiosValidator(nagios_bin=str(binary))
        exists, msg = v.check_binary_exists()
        assert exists is False
        assert "not executable" in msg

    def test_existing_executable(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh\necho hi")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))
        exists, msg = v.check_binary_exists()
        assert exists is True


class TestVerifyBinary:
    """Tests for NagiosValidator.verify_binary with mocked subprocess."""

    def test_valid_nagios_binary(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Nagios Core 4.4.6\nCopyright...\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = v.verify_binary()
        assert result.success is True
        assert "4.4.6" in result.data

    def test_non_nagios_binary(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Apache HTTP Server\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = v.verify_binary()
        assert result.success is False
        assert "does not appear to be Nagios" in result.error

    def test_timeout(self, tmp_path):
        binary = tmp_path / "nagios"
        binary.write_text("#!/bin/sh")
        binary.chmod(stat.S_IRWXU)
        v = NagiosValidator(nagios_bin=str(binary))

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = v.verify_binary()
        assert result.success is False
        assert "timed out" in result.error
