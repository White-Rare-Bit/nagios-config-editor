"""
Tests for validator.py - Nagios Configuration Validator
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validator import NagiosValidator, ValidationResult, validate_config


class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = ValidationResult(
            success=True,
            errors=[],
            warnings=[{'message': 'Test warning'}],
            total_errors=0,
            total_warnings=1,
            raw_output='Test output'
        )
        d = result.to_dict()

        assert d['success'] is True
        assert d['errors'] == []
        assert len(d['warnings']) == 1
        assert d['total_errors'] == 0
        assert d['total_warnings'] == 1
        assert d['raw_output'] == 'Test output'

    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        result = ValidationResult(
            success=False,
            errors=[
                {'file': '/etc/nagios/hosts.cfg', 'line': 10, 'message': 'Invalid host'},
                {'message': 'General error'}
            ],
            warnings=[],
            total_errors=2,
            total_warnings=0,
            raw_output='Error output'
        )

        assert result.success is False
        assert len(result.errors) == 2
        assert result.total_errors == 2


class TestNagiosValidator:
    """Tests for the NagiosValidator class."""

    def test_init_default_paths(self):
        """Test initialization with default paths."""
        validator = NagiosValidator()
        assert validator.config_file == './sample-config/nagios.cfg'

    def test_init_custom_paths(self):
        """Test initialization with custom paths."""
        validator = NagiosValidator(
            nagios_bin='/custom/path/nagios',
            config_file='/custom/nagios.cfg'
        )
        assert validator.nagios_bin == '/custom/path/nagios'
        assert validator.config_file == '/custom/nagios.cfg'

    def test_check_binary_exists_not_found(self):
        """Test check_binary_exists when binary doesn't exist."""
        validator = NagiosValidator(nagios_bin='/nonexistent/path/nagios')
        exists, message = validator.check_binary_exists()

        assert exists is False
        assert 'not found' in message

    @patch('os.path.exists')
    @patch('os.access')
    def test_check_binary_exists_found(self, mock_access, mock_exists):
        """Test check_binary_exists when binary exists and is executable."""
        mock_exists.return_value = True
        mock_access.return_value = True

        validator = NagiosValidator(nagios_bin='/usr/sbin/nagios')
        exists, message = validator.check_binary_exists()

        assert exists is True
        assert message == '/usr/sbin/nagios'

    @patch('os.path.exists')
    @patch('os.access')
    def test_check_binary_exists_not_executable(self, mock_access, mock_exists):
        """Test check_binary_exists when binary exists but is not executable."""
        mock_exists.return_value = True
        mock_access.return_value = False

        validator = NagiosValidator(nagios_bin='/usr/sbin/nagios')
        exists, message = validator.check_binary_exists()

        assert exists is False
        assert 'not executable' in message

    def test_validate_binary_not_found(self):
        """Test validation when binary doesn't exist."""
        validator = NagiosValidator(nagios_bin='/nonexistent/nagios')
        result = validator.validate()

        assert result.success is False
        assert len(result.errors) == 1
        assert 'not found' in result.errors[0]['message']

    def test_validate_config_not_found(self, temp_config_dir):
        """Test validation when config file doesn't exist."""
        # Create a fake nagios binary path that "exists"
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda p: p == '/usr/sbin/nagios'
            validator = NagiosValidator(
                nagios_bin='/usr/sbin/nagios',
                config_file='/nonexistent/nagios.cfg'
            )
            result = validator.validate()

        assert result.success is False
        assert 'not found' in result.errors[0]['message'].lower()

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_success(self, mock_exists, mock_run):
        """Test successful validation."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Things look okay - No serious problems were detected\nTotal Warnings: 0\nTotal Errors: 0',
            stderr=''
        )

        validator = NagiosValidator()
        result = validator.validate()

        assert result.success is True
        assert result.total_errors == 0

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_with_errors(self, mock_exists, mock_run):
        """Test validation with errors."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="Error: Could not find host 'test-server'\nTotal Errors: 1",
            stderr=''
        )

        validator = NagiosValidator()
        result = validator.validate()

        assert result.success is False
        assert result.total_errors == 1

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_with_warnings(self, mock_exists, mock_run):
        """Test validation with warnings."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Warning: Host has no services\nTotal Warnings: 1\nTotal Errors: 0",
            stderr=''
        )

        validator = NagiosValidator()
        result = validator.validate()

        assert result.success is True
        assert result.total_warnings == 1

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_timeout(self, mock_exists, mock_run):
        """Test validation timeout handling."""
        import subprocess
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='nagios', timeout=60)

        validator = NagiosValidator()
        result = validator.validate()

        assert result.success is False
        assert 'timed out' in result.errors[0]['message'].lower()

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_exception(self, mock_exists, mock_run):
        """Test validation exception handling."""
        mock_exists.return_value = True
        mock_run.side_effect = Exception('Unexpected error')

        validator = NagiosValidator()
        result = validator.validate()

        assert result.success is False
        assert 'Failed to run validation' in result.errors[0]['message']

    def test_parse_output_success(self):
        """Test parsing successful output."""
        validator = NagiosValidator()
        output = '''
Nagios Core 4.4.6
Reading configuration data...
Running pre-flight check on configuration data...

Checking objects...
Checked 10 objects

Total Warnings: 0
Total Errors:   0

Things look okay - No serious problems were detected during the pre-flight check
'''
        result = validator._parse_output(output, True)

        assert result.success is True
        assert result.total_errors == 0
        assert result.total_warnings == 0

    def test_parse_output_with_errors(self):
        """Test parsing output with errors."""
        validator = NagiosValidator()
        output = '''
Error: Could not find host 'missing-host' for service 'HTTP'
Error in file '/etc/nagios/services.cfg' on line 42: Invalid service definition

Total Warnings: 0
Total Errors:   2
'''
        result = validator._parse_output(output, False)

        assert result.success is False
        assert result.total_errors == 2
        assert len(result.errors) == 2

    def test_parse_output_with_file_line_info(self):
        """Test parsing errors with file and line information."""
        validator = NagiosValidator()
        output = "Error in file '/etc/nagios/hosts.cfg' on line 15: Invalid host definition"

        result = validator._parse_output(output, False)

        assert len(result.errors) == 1
        assert result.errors[0]['file'] == '/etc/nagios/hosts.cfg'
        assert result.errors[0]['line'] == 15
        assert 'Invalid host definition' in result.errors[0]['message']

    def test_parse_output_with_warnings(self):
        """Test parsing output with warnings."""
        validator = NagiosValidator()
        output = '''
Warning: Host 'test-server' has no services associated with it
Warning: Contact 'admin' has no notification commands

Total Warnings: 2
Total Errors:   0
'''
        result = validator._parse_output(output, True)

        assert result.success is True
        assert result.total_warnings == 2
        assert len(result.warnings) == 2

    def test_parse_output_mixed(self):
        """Test parsing output with both errors and warnings."""
        validator = NagiosValidator()
        output = '''
Warning: Host has no services
Error: Invalid command 'bad_command'

Total Warnings: 1
Total Errors:   1
'''
        result = validator._parse_output(output, False)

        assert result.success is False
        assert result.total_errors == 1
        assert result.total_warnings == 1

    def test_parse_output_config_error(self):
        """Test parsing CONFIG ERROR format."""
        validator = NagiosValidator()
        output = "CONFIG ERROR: Missing required field 'host_name'"

        result = validator._parse_output(output, False)

        assert len(result.errors) == 1

    def test_parse_output_config_warning(self):
        """Test parsing CONFIG WARNING format."""
        validator = NagiosValidator()
        output = "CONFIG WARNING: Deprecated directive used"

        result = validator._parse_output(output, True)

        assert len(result.warnings) == 1


class TestValidateConfigConvenience:
    """Tests for the validate_config convenience function."""

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_validate_config(self, mock_exists, mock_run):
        """Test the validate_config convenience function."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Total Errors: 0',
            stderr=''
        )

        result = validate_config()
        assert isinstance(result, ValidationResult)

    def test_validate_config_custom_paths(self):
        """Test validate_config with custom paths."""
        result = validate_config(
            nagios_bin='/nonexistent/nagios',
            config_file='/nonexistent/nagios.cfg'
        )
        # Should fail because paths don't exist
        assert result.success is False
