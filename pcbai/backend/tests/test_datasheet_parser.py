"""
Tests for datasheet_parser.py

Run with:  pytest pcbai/backend/tests/test_datasheet_parser.py -v

These tests cover:
  - _dict_to_constraints: JSON → DatasheetConstraints mapping
  - _heuristic_parse: regex-based fallback on raw text
  - DatasheetConstraints.beginner_summary() and expert_summary()
  - DatasheetParser._to_response() output shape
  - Cache behaviour
  - Malformed / edge-case input handling
"""

import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from datasheet_parser import (
    DatasheetParser,
    DatasheetConstraints,
    _dict_to_constraints,
    _heuristic_parse,
    Pin, DecouplingRequirement, LayoutNote,
    AbsMaxRatings, OperatingConditions,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

FULL_CLAUDE_JSON = {
    "component_name": "LM358",
    "manufacturer": "Texas Instruments",
    "package": "SOIC-8",
    "pins": [
        {"number": "1", "name": "OUT1",  "function": "Output 1",           "notes": ""},
        {"number": "2", "name": "IN1-",  "function": "Inverting input 1",  "notes": ""},
        {"number": "3", "name": "IN1+",  "function": "Non-inverting inp 1","notes": ""},
        {"number": "4", "name": "GND",   "function": "Ground",             "notes": ""},
        {"number": "5", "name": "IN2+",  "function": "Non-inverting inp 2","notes": ""},
        {"number": "6", "name": "IN2-",  "function": "Inverting input 2",  "notes": ""},
        {"number": "7", "name": "OUT2",  "function": "Output 2",           "notes": ""},
        {"number": "8", "name": "VCC",   "function": "Positive supply",    "notes": ""},
    ],
    "decoupling": [
        {"pin_or_net": "VCC", "value_uf": 0.1, "type": "ceramic MLCC",
         "max_distance_mm": 1.0, "notes": "100nF bypass"},
        {"pin_or_net": "VCC", "value_uf": 10.0, "type": "electrolytic",
         "max_distance_mm": 10.0, "notes": "bulk cap"},
    ],
    "layout_notes": [
        {"category": "general",  "description": "Decouple VCC with 100nF close to pin 8", "critical": False},
        {"category": "routing",  "description": "Keep high-gain feedback traces short",    "critical": True},
    ],
    "abs_max": {
        "vcc_max_v": 32.0, "vcc_min_v": -0.3, "icc_max_ma": 3.0,
        "power_max_mw": 830, "temp_max_c": 125, "temp_min_c": -40,
    },
    "operating": {
        "vcc_nom_v": 12.0, "vcc_range_v": [3.0, 32.0],
        "icc_typical_ma": 0.7, "icc_max_ma": 1.2, "freq_max_mhz": 1.0,
    },
    "impedance_requirements": [],
    "differential_pairs": [],
    "footprint_notes": "Standard SOIC-8, no special requirements",
}

USB_FS_CHIP_JSON = {
    "component_name": "CH340G",
    "manufacturer": "WCH",
    "package": "SOP-16",
    "pins": [{"number": str(i), "name": f"PIN{i}", "function": "pin", "notes": ""} for i in range(1, 17)],
    "decoupling": [
        {"pin_or_net": "VCC", "value_uf": 0.1, "type": "ceramic", "max_distance_mm": 1.0, "notes": ""},
        {"pin_or_net": "V3",  "value_uf": 0.1, "type": "ceramic", "max_distance_mm": 1.0, "notes": "3.3V LDO output cap"},
    ],
    "layout_notes": [
        {"category": "routing", "description": "USB D+/D- traces must be matched length ±0.5mm", "critical": True},
        {"category": "routing", "description": "Minimize via count on USB traces", "critical": True},
    ],
    "abs_max": {"vcc_max_v": 5.5, "vcc_min_v": -0.3, "icc_max_ma": 30, "power_max_mw": None, "temp_max_c": 85, "temp_min_c": -40},
    "operating": {"vcc_nom_v": 5.0, "vcc_range_v": [4.5, 5.5], "icc_typical_ma": 20, "icc_max_ma": 30, "freq_max_mhz": None},
    "impedance_requirements": [
        {"net_or_pair": "USB_DP/USB_DM", "target_ohms": 90, "tolerance_pct": 10, "layer_notes": "differential microstrip"},
    ],
    "differential_pairs": [
        {"positive_pin": "UD+", "negative_pin": "UD-", "net_base_name": "USB", "max_skew_mm": 0.5, "impedance_ohms": 90},
    ],
    "footprint_notes": "",
}

THERMAL_PAD_JSON = {
    "component_name": "TPS62840",
    "manufacturer": "Texas Instruments",
    "package": "WSON-6",
    "pins": [{"number": str(i), "name": f"P{i}", "function": "", "notes": ""} for i in range(1, 7)],
    "decoupling": [
        {"pin_or_net": "VIN", "value_uf": 1.0, "type": "ceramic X5R", "max_distance_mm": 0.5, "notes": "1µF input cap"},
        {"pin_or_net": "VOUT", "value_uf": 10.0, "type": "ceramic X5R", "max_distance_mm": 1.0, "notes": "10µF output cap"},
    ],
    "layout_notes": [
        {"category": "thermal", "description": "Exposed pad on bottom must connect to GND plane via 4 vias min", "critical": True},
        {"category": "routing", "description": "SW node trace must be as short and wide as possible", "critical": True},
        {"category": "ground_plane", "description": "Solid GND pour under entire IC", "critical": False},
    ],
    "abs_max": {"vcc_max_v": 5.5, "vcc_min_v": -0.3, "icc_max_ma": 750, "power_max_mw": None, "temp_max_c": 125, "temp_min_c": -40},
    "operating": {"vcc_nom_v": 3.3, "vcc_range_v": [1.8, 5.5], "icc_typical_ma": 60, "icc_max_ma": 750, "freq_max_mhz": 2.0},
    "impedance_requirements": [],
    "differential_pairs": [],
    "footprint_notes": "Exposed pad 1.2mm x 1.4mm, connect to GND with min 4 thermal vias",
}


# ── _dict_to_constraints ──────────────────────────────────────────────────────

class TestDictToConstraints:
    def test_basic_fields(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        assert c.component_name == "LM358"
        assert c.manufacturer == "Texas Instruments"
        assert c.package == "SOIC-8"
        assert c.filename == "lm358.pdf"

    def test_pin_count(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        assert len(c.pins) == 8
        assert c.pins[0].number == "1"
        assert c.pins[0].name == "OUT1"

    def test_decoupling(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        assert len(c.decoupling) == 2
        assert c.decoupling[0].value_uf == 0.1
        assert c.decoupling[0].type == "ceramic MLCC"
        assert c.decoupling[0].max_distance_mm == 1.0

    def test_abs_max(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        assert c.abs_max.vcc_max_v == 32.0
        assert c.abs_max.temp_max_c == 125
        assert c.abs_max.temp_min_c == -40

    def test_operating_conditions(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        assert c.operating.vcc_nom_v == 12.0
        assert c.operating.vcc_range_v == (3.0, 32.0)
        assert c.operating.icc_typical_ma == 0.7

    def test_layout_notes_critical(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        critical = [n for n in c.layout_notes if n.critical]
        assert len(critical) == 1
        assert "feedback" in critical[0].description

    def test_differential_pairs(self):
        c = _dict_to_constraints("usb.pdf", USB_FS_CHIP_JSON)
        assert len(c.differential_pairs) == 1
        dp = c.differential_pairs[0]
        assert dp.positive_pin == "UD+"
        assert dp.negative_pin == "UD-"
        assert dp.impedance_ohms == 90.0
        assert dp.max_skew_mm == 0.5

    def test_impedance_requirements(self):
        c = _dict_to_constraints("usb.pdf", USB_FS_CHIP_JSON)
        assert len(c.impedance_requirements) == 1
        req = c.impedance_requirements[0]
        assert req.target_ohms == 90.0
        assert req.tolerance_pct == 10.0

    def test_thermal_pad_notes(self):
        c = _dict_to_constraints("tps.pdf", THERMAL_PAD_JSON)
        critical = [n for n in c.layout_notes if n.critical]
        assert any("thermal" in n.category for n in critical)

    def test_footprint_notes(self):
        c = _dict_to_constraints("tps.pdf", THERMAL_PAD_JSON)
        assert "GND" in c.footprint_notes

    def test_null_fields_handled(self):
        sparse = {
            "component_name": "CHIP", "manufacturer": None, "package": None,
            "pins": [], "decoupling": [], "layout_notes": [],
            "abs_max": {}, "operating": {"vcc_range_v": None},
            "impedance_requirements": [], "differential_pairs": [],
            "footprint_notes": None,
        }
        c = _dict_to_constraints("x.pdf", sparse)
        assert c.component_name == "CHIP"
        assert c.manufacturer == ""
        assert c.abs_max.vcc_max_v is None
        assert c.operating.vcc_range_v is None

    def test_parse_method_set(self):
        c = _dict_to_constraints("x.pdf", FULL_CLAUDE_JSON)
        assert c.parse_method == "claude"
        assert c.confidence == 0.85


# ── _heuristic_parse ──────────────────────────────────────────────────────────

class TestHeuristicParse:
    SAMPLE_DATASHEET_TEXT = """\
LM7805 Voltage Regulator
Texas Instruments

ABSOLUTE MAXIMUM RATINGS
Input Voltage (VCC): 35V max, minimum -0.3V
Output Current: 1500mA max
Power Dissipation: 15W max
Operating Temperature: -40°C to 125°C

RECOMMENDED DECOUPLING
Place 100nF ceramic capacitor close to input.
Place 10µF electrolytic capacitor on output.
Optional: 100nF ceramic bypass on output.

LAYOUT NOTES
This device has an exposed thermal pad that must be soldered to the PCB.
The thermal pad should be connected to a solid ground plane.
"""

    def test_component_name_extracted(self):
        c = _heuristic_parse("lm7805.pdf", self.SAMPLE_DATASHEET_TEXT)
        assert "LM7805" in c.component_name

    def test_abs_max_voltage(self):
        c = _heuristic_parse("lm7805.pdf", self.SAMPLE_DATASHEET_TEXT)
        assert c.abs_max.vcc_max_v == 35.0

    def test_decoupling_extracted(self):
        c = _heuristic_parse("lm7805.pdf", self.SAMPLE_DATASHEET_TEXT)
        assert len(c.decoupling) >= 1
        values = [d.value_uf for d in c.decoupling]
        assert any(abs(v - 0.1) < 0.01 for v in values), f"100nF not found in {values}"

    def test_thermal_pad_critical_note(self):
        c = _heuristic_parse("lm7805.pdf", self.SAMPLE_DATASHEET_TEXT)
        assert any(n.critical and "thermal" in n.category for n in c.layout_notes)

    def test_empty_text(self):
        c = _heuristic_parse("empty.pdf", "")
        assert c.parse_method == "heuristic"
        assert len(c.pins) == 0

    def test_parse_method(self):
        c = _heuristic_parse("x.pdf", "Some text with no matches")
        assert c.parse_method == "heuristic"
        assert c.confidence == 0.3


# ── Summary generation ────────────────────────────────────────────────────────

class TestSummaries:
    def test_beginner_summary_has_component_name(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        summary = c.beginner_summary()
        assert "LM358" in summary

    def test_beginner_summary_mentions_decoupling(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        summary = c.beginner_summary()
        assert "Decoupling" in summary or "decoupling" in summary.lower()

    def test_beginner_summary_shows_critical_notes(self):
        c = _dict_to_constraints("tps.pdf", THERMAL_PAD_JSON)
        summary = c.beginner_summary()
        assert "Critical" in summary or "⚠️" in summary

    def test_beginner_summary_shows_voltage(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        summary = c.beginner_summary()
        assert "32.0" in summary or "12.0" in summary

    def test_expert_summary_compact(self):
        c = _dict_to_constraints("lm358.pdf", FULL_CLAUDE_JSON)
        summary = c.expert_summary()
        assert "LM358" in summary
        assert "SOIC-8" in summary
        # Should fit on ~2 lines — not excessively long
        assert len(summary) < 500

    def test_expert_summary_shows_diff_pairs(self):
        c = _dict_to_constraints("usb.pdf", USB_FS_CHIP_JSON)
        summary = c.expert_summary()
        assert "USB" in summary
        assert "90" in summary   # impedance

    def test_to_dict_serializable(self):
        """Verify the constraints are JSON-serializable."""
        import json
        c = _dict_to_constraints("tps.pdf", THERMAL_PAD_JSON)
        d = c.to_dict()
        serialized = json.dumps(d)  # Should not raise
        assert '"component_name"' in serialized


# ── DatasheetParser (no-client mode) ─────────────────────────────────────────

class TestDatasheetParser:
    """Tests using the parser without a Claude client (heuristic-only mode).

    PDF extraction is mocked to bypass pdfplumber/PyMuPDF library issues in the
    test environment. We test the parser logic, not the PDF reading library.
    """

    FAKE_PDF = b"%PDF-1.4 fake"
    FAKE_TEXT = "LM358 Op-Amp\nSupply Voltage VCC: 32V max\n100nF ceramic bypass on VCC pin\nExposed thermal pad must connect to GND."

    def _make_parser(self):
        return DatasheetParser(anthropic_client=None)

    def test_parse_returns_dict(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            result = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        assert isinstance(result, dict)
        assert "parsed" in result

    def test_parse_empty_returns_error(self):
        parser = self._make_parser()
        result = asyncio.run(parser.parse("empty.pdf", b""))
        assert result["parsed"] is False
        assert "error" in result

    def test_parse_result_has_required_keys(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            result = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        for key in ("filename", "confidence", "parse_method", "constraints"):
            assert key in result, f"Missing key: {key}"

    def test_parse_result_constraints_has_shape(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            result = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        c = result["constraints"]
        assert "pins" in c
        assert "decoupling" in c
        assert "layout_notes" in c
        assert "abs_max" in c

    def test_heuristic_extracts_voltage_from_text(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            result = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        assert result["constraints"]["abs_max"]["vcc_max_v"] == 32.0

    def test_heuristic_extracts_thermal_note(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            result = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        critical = result["critical_layout_notes"]
        assert len(critical) >= 1

    def test_cache_hit(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            r1 = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
            r2 = asyncio.run(parser.parse("test.pdf", self.FAKE_PDF))
        assert r2.get("cached") is True

    def test_cache_miss_different_content(self):
        parser = self._make_parser()
        with patch("datasheet_parser._extract_text_pdfplumber", return_value=(self.FAKE_TEXT, [])):
            r1 = asyncio.run(parser.parse("a.pdf", self.FAKE_PDF))
            r2 = asyncio.run(parser.parse("b.pdf", self.FAKE_PDF + b" extra"))
        assert r2.get("cached") is False
