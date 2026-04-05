"""
Tests for expertise_detector.py

Run with:  pytest pcbai/backend/tests/test_expertise_detector.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from expertise_detector import ExpertiseDetector, quick_classify


# ── Single-message classification ────────────────────────────────────────────

class TestQuickClassify:
    def test_strong_expert_packages(self):
        assert quick_classify("I need a 220 ohm resistor in 0402 package") == "expert"

    def test_strong_expert_standards(self):
        assert quick_classify("IPC-2221 trace widths on 1oz copper, 10°C rise") == "expert"

    def test_strong_expert_terminology(self):
        assert quick_classify(
            "I'm designing a 4-layer stackup with controlled impedance "
            "differential pairs for USB 3.0 signal integrity"
        ) == "expert"

    def test_strong_expert_part_number(self):
        assert quick_classify("Using a TPS62840 buck converter with 100mA output at 3.3V") == "expert"

    def test_strong_expert_layout(self):
        assert quick_classify(
            "Need via stitching around the RF section with thermal relief on "
            "all power pads. QFN-48 footprint, ENIG surface finish."
        ) == "expert"

    def test_beginner_function_description(self):
        assert quick_classify("I want something that turns on an LED when it gets dark") == "beginner"

    def test_beginner_consumer_language(self):
        assert quick_classify("I need a board that connects to my phone app over bluetooth") == "beginner"

    def test_beginner_explicit(self):
        assert quick_classify("I'm new to PCB design, can you explain what a trace is?") == "beginner"

    def test_beginner_vague(self):
        assert quick_classify("I just need a circuit that can make a motor spin") == "beginner"

    def test_unknown_insufficient(self):
        # Single short message, no strong signals either way
        assert quick_classify("I need a power supply board") == "unknown"

    def test_unknown_neutral(self):
        assert quick_classify("Hello, I want to design a PCB") == "unknown"


# ── Multi-turn session accuracy ───────────────────────────────────────────────

class TestSessionAccumulation:
    def test_expert_builds_over_messages(self):
        d = ExpertiseDetector()
        d.analyze("I need a buck converter circuit")        # weak signal
        d.analyze("Using TMC2209 stepper drivers, QFN package")  # strong
        d.analyze("4-layer stackup, 1oz copper, IPC-2221 trace widths")  # very strong
        assert d.level() == "expert"
        assert d.confidence() > 0.5

    def test_beginner_builds_over_messages(self):
        d = ExpertiseDetector()
        d.analyze("I'm new to this, can you explain how it works?")
        d.analyze("I just want something that turns on a light")
        d.analyze("I don't understand what a resistor does")
        assert d.level() == "beginner"

    def test_mixed_detection(self):
        d = ExpertiseDetector()
        d.analyze("I need a TPS5430 buck converter, QFN package, IPC-2221 traces")
        d.analyze("I don't understand how to connect it to my phone app")
        assert d.level() in ("mixed", "expert")  # expert signals dominate but contamination present

    def test_unknown_clears_to_expert_with_signal(self):
        d = ExpertiseDetector()
        d.analyze("I want to design a PCB")           # unknown
        assert d.level() == "unknown"
        d.analyze("The stackup is 4-layer, 1oz copper, FR4, 0.8mm dielectric, "
                  "50-ohm controlled impedance on differential pairs")
        assert d.level() == "expert"

    def test_confidence_increases_with_messages(self):
        d = ExpertiseDetector()
        d.analyze("I need a 0402 resistor")
        c1 = d.confidence()
        d.analyze("IPC-2221 trace widths, QFN package, ENIG finish")
        c2 = d.confidence()
        assert c2 > c1

    def test_reset_clears_state(self):
        d = ExpertiseDetector()
        d.analyze("IPC-2221, QFN, 0402, differential pairs, impedance")
        assert d.level() == "expert"
        d.reset()
        assert d.level() == "unknown"
        assert d.confidence() == 0.0


# ── Domain breakdown ──────────────────────────────────────────────────────────

class TestDomainBreakdown:
    def test_power_domain_expert(self):
        d = ExpertiseDetector()
        d.analyze("LDO with 100mA current limit, bypass caps 100nF + 10µF, thermal pad")
        breakdown = d.domain_breakdown()
        assert breakdown.get("power") == "expert"

    def test_signal_integrity_domain(self):
        d = ExpertiseDetector()
        d.analyze("Controlled impedance 50-ohm microstrip, length-matched differential pairs at 480MHz")
        breakdown = d.domain_breakdown()
        assert breakdown.get("signal_integrity") == "expert"

    def test_components_domain_packages(self):
        d = ExpertiseDetector()
        d.analyze("Using 0402 caps and SOT-23 transistors, QFN-48 for the MCU")
        breakdown = d.domain_breakdown()
        assert breakdown.get("components") == "expert"

    def test_standards_domain(self):
        d = ExpertiseDetector()
        d.analyze("Must comply with IPC-2221 for trace widths and IPC-7351 for land patterns")
        breakdown = d.domain_breakdown()
        assert breakdown.get("standards") == "expert"


# ── Summary output ────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_has_required_keys(self):
        d = ExpertiseDetector()
        d.analyze("I need a QFN-48 MCU with 100mA LDO")
        s = d.summary()
        assert "level" in s
        assert "confidence" in s
        assert "expert_score" in s
        assert "beginner_score" in s
        assert "message_count" in s
        assert "domain_breakdown" in s

    def test_message_count_increments(self):
        d = ExpertiseDetector()
        assert d.summary()["message_count"] == 0
        d.analyze("msg 1")
        d.analyze("msg 2")
        assert d.summary()["message_count"] == 2


# ── Real-world examples from spec ────────────────────────────────────────────

class TestSpecExamples:
    """Test cases directly drawn from the project specification."""

    def test_spec_expert_example_3d_printer(self):
        """'I want a 3D printer controller with TMC2209 drivers, ESP32, and 24V input.'
        The spec says this should be handled as a potentially expert-level request
        if more detail is provided. TMC2209 is a specific part number signal."""
        d = ExpertiseDetector()
        d.analyze("I want a 3D printer controller with TMC2209 drivers, ESP32, and 24V input")
        # TMC2209 is a full part number — expert signal
        assert d.level() in ("expert", "unknown")  # may need more messages for full confidence

    def test_spec_beginner_motor_controller(self):
        """'something that controls a motor' → beginner signal."""
        d = ExpertiseDetector()
        d.analyze("I want something that controls a motor")
        assert d.level() in ("beginner", "unknown")

    def test_spec_beginner_phone_connect(self):
        """'make it connect to my phone' → strong beginner signal."""
        assert quick_classify("make it connect to my phone") == "beginner"

    def test_spec_expert_ipc_reference(self):
        """Referencing IPC-2221 → very strong expert signal."""
        assert quick_classify("Using IPC-2221 for trace width calculations") == "expert"

    def test_spec_expert_package_unprompted(self):
        """Specifying packages without being asked → expert."""
        assert quick_classify(
            "I need a 47µF 0805 cap and a 10kΩ 0402 resistor"
        ) == "expert"
