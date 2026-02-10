"""Tests for timeperiod date-range parsing (BUG-1)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from nagios_parser import NagiosConfigParser


@pytest.fixture
def parser_with_timeperiods():
    """Create parser with complex timeperiod configs."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name         complex-schedule
    alias                   Complex Schedule

    monday                  09:00-17:00
    tuesday                 09:00-17:00

    monday 1                08:00-12:00
    monday 2                08:00-12:00,13:00-17:00
    monday -1               00:00-24:00

    day 1 - 15              08:00-17:00
    day 20 - -1             08:00-17:00

    january 1               00:00-24:00
    june 1 - june 15        00:00-24:00

    2025-01-01              00:00-24:00
    2025-12-24 - 2025-12-26 00:00-24:00

    monday 3 - thursday 4   00:00-24:00

    april 10 - may 15       00:00-24:00
}

define timeperiod {
    timeperiod_name         simple-schedule
    alias                   Simple
    monday                  09:00-17:00
    friday                  00:00-09:00,17:00-24:00
}
""")

    parser = NagiosConfigParser(str(test_config_path))
    parser.parse_all()

    yield parser

    shutil.rmtree(test_dir, ignore_errors=True)


class TestTimeperiodParsing:
    """Test that timeperiod date-range keys are parsed correctly."""

    def test_simple_day_names(self, parser_with_timeperiods):
        """Simple day names (monday, friday) parse normally."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "simple-schedule":
                tp = obj
                break
        assert tp is not None
        assert tp.attributes["monday"] == "09:00-17:00"
        assert tp.attributes["friday"] == "00:00-09:00,17:00-24:00"

    def test_weekday_occurrence(self, parser_with_timeperiods):
        """Weekday with occurrence number: 'monday 1' should be key."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "monday 1" in tp.attributes
        assert tp.attributes["monday 1"] == "08:00-12:00"
        assert "monday 2" in tp.attributes
        assert tp.attributes["monday 2"] == "08:00-12:00,13:00-17:00"
        assert "monday -1" in tp.attributes
        assert tp.attributes["monday -1"] == "00:00-24:00"

    def test_day_of_month_ranges(self, parser_with_timeperiods):
        """Day-of-month ranges: 'day 1 - 15' should be key."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "day 1 - 15" in tp.attributes
        assert tp.attributes["day 1 - 15"] == "08:00-17:00"
        assert "day 20 - -1" in tp.attributes
        assert tp.attributes["day 20 - -1"] == "08:00-17:00"

    def test_month_day_directives(self, parser_with_timeperiods):
        """Month-day directives: 'january 1', 'june 1 - june 15'."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "january 1" in tp.attributes
        assert tp.attributes["january 1"] == "00:00-24:00"
        assert "june 1 - june 15" in tp.attributes
        assert tp.attributes["june 1 - june 15"] == "00:00-24:00"

    def test_specific_dates(self, parser_with_timeperiods):
        """Specific calendar dates: '2025-01-01', '2025-12-24 - 2025-12-26'."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "2025-01-01" in tp.attributes
        assert tp.attributes["2025-01-01"] == "00:00-24:00"
        assert "2025-12-24 - 2025-12-26" in tp.attributes
        assert tp.attributes["2025-12-24 - 2025-12-26"] == "00:00-24:00"

    def test_weekday_ranges(self, parser_with_timeperiods):
        """Weekday ranges: 'monday 3 - thursday 4'."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "monday 3 - thursday 4" in tp.attributes
        assert tp.attributes["monday 3 - thursday 4"] == "00:00-24:00"

    def test_month_date_ranges(self, parser_with_timeperiods):
        """Month date ranges: 'april 10 - may 15'."""
        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None
        assert "april 10 - may 15" in tp.attributes
        assert tp.attributes["april 10 - may 15"] == "00:00-24:00"

    def test_round_trip_preserves_timeperiods(self, parser_with_timeperiods):
        """Writing and re-reading a timeperiod preserves date-range keys."""
        import os

        from nagios_writer import NagiosConfigWriter

        tp = None
        for obj in parser_with_timeperiods.objects:
            if obj.attributes.get("timeperiod_name") == "complex-schedule":
                tp = obj
                break
        assert tp is not None

        # Write to temp file
        test_dir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(test_dir, "out.cfg")
            writer = NagiosConfigWriter()
            writer.write_file(out_path, [tp])

            # Re-parse
            parser2 = NagiosConfigParser(test_dir)
            parser2.parse_all()

            tp2 = None
            for obj in parser2.objects:
                if obj.attributes.get("timeperiod_name") == "complex-schedule":
                    tp2 = obj
                    break
            assert tp2 is not None
            assert "monday 1" in tp2.attributes
            assert "day 1 - 15" in tp2.attributes
            assert "2025-01-01" in tp2.attributes
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
