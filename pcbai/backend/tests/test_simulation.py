"""
Tests for the PCB.AI simulation engine.
Covers PowerBudgetCalculator, TraceWidthCalculator, ImpedanceCalculator,
and SPICEGenerator.
"""

import math
import pytest

from simulation.power_budget import PowerBudgetCalculator
from simulation.trace_width import TraceWidthCalculator
from simulation.impedance import ImpedanceCalculator
from simulation.spice_generator import SPICEGenerator, _parse_value, _fmt


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def approx(v, rel=0.02):
    """Return a pytest.approx with 2% relative tolerance by default."""
    return pytest.approx(v, rel=rel)


# ═════════════════════════════════════════════════════════════════════════════
# PowerBudgetCalculator
# ═════════════════════════════════════════════════════════════════════════════

class TestPowerBudgetCalculator:
    pbc = PowerBudgetCalculator()

    def test_empty_components(self):
        result = self.pbc.check([])
        assert result["passed"] is True
        assert result["total_current_ma"] == 0.0
        assert result["total_power_mw"] == 0.0
        assert result["regulator_capacity_ma"] is None
        assert result["margin_pct"] is None

    def test_single_load_no_regulator(self):
        comp = {"ref": "U1", "type": "mcu", "current_ma": 50.0, "voltage_v": 3.3}
        result = self.pbc.check([comp])
        assert result["passed"] is True
        assert result["total_current_ma"] == approx(50.0)
        assert result["total_power_mw"] == approx(50.0 * 3.3)
        assert result["regulator_capacity_ma"] is None

    def test_regulator_identified_by_type(self):
        comps = [
            {"ref": "U1", "type": "ldo", "capacity_ma": 500.0},
            {"ref": "U2", "type": "mcu", "current_ma": 100.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        assert result["regulator_capacity_ma"] == approx(500.0)
        assert result["total_current_ma"] == approx(100.0)
        # margin = (500 - 100) / 500 = 80%
        assert result["margin_pct"] == approx(80.0)
        assert result["passed"] is True

    def test_regulator_identified_by_is_regulator_flag(self):
        comps = [
            {"ref": "VR1", "type": "custom", "is_regulator": True, "capacity_ma": 200.0},
            {"ref": "R1", "type": "resistor", "current_ma": 10.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        assert result["regulator_capacity_ma"] == approx(200.0)
        assert result["passed"] is True

    def test_margin_fail_below_20_pct(self):
        comps = [
            {"ref": "U1", "type": "ldo", "capacity_ma": 100.0},
            {"ref": "U2", "type": "mcu", "current_ma": 90.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        # margin = (100 - 90) / 100 = 10% → below 20% threshold
        assert result["passed"] is False
        assert result["margin_pct"] == approx(10.0)
        assert len(result["issues"]) >= 1
        assert "margin" in result["issues"][0].lower()

    def test_margin_exactly_at_threshold_passes(self):
        comps = [
            {"ref": "U1", "type": "ldo", "capacity_ma": 100.0},
            {"ref": "U2", "type": "mcu", "current_ma": 80.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        assert result["margin_pct"] == approx(20.0)
        assert result["passed"] is True

    def test_thermal_warning_above_500mw(self):
        comps = [
            {"ref": "Q1", "type": "mosfet", "current_ma": 200.0, "power_mw": 800.0},
        ]
        result = self.pbc.check(comps)
        assert len(result["thermal_warnings"]) == 1
        assert "Q1" in result["thermal_warnings"][0]

    def test_thermal_warning_below_threshold_no_warning(self):
        comps = [
            {"ref": "Q1", "type": "mosfet", "current_ma": 50.0, "power_mw": 400.0},
        ]
        result = self.pbc.check(comps)
        assert result["thermal_warnings"] == []

    def test_explicit_power_mw_overrides_vi(self):
        comps = [
            {"ref": "U1", "type": "mcu", "current_ma": 100.0, "voltage_v": 3.3, "power_mw": 250.0},
        ]
        result = self.pbc.check(comps)
        assert result["total_power_mw"] == approx(250.0)

    def test_multiple_regulators_sum_capacity(self):
        comps = [
            {"ref": "U1", "type": "ldo", "capacity_ma": 300.0},
            {"ref": "U2", "type": "buck", "capacity_ma": 400.0},
            {"ref": "U3", "type": "mcu", "current_ma": 200.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        assert result["regulator_capacity_ma"] == approx(700.0)
        # margin = (700 - 200) / 700 ≈ 71.4%
        assert result["margin_pct"] == approx(71.4, rel=0.01)
        assert result["passed"] is True

    def test_component_details_in_output(self):
        comps = [
            {"ref": "U1", "type": "mcu", "current_ma": 50.0, "voltage_v": 3.3},
        ]
        result = self.pbc.check(comps)
        assert len(result["components"]) == 1
        assert result["components"][0]["ref"] == "U1"
        assert result["components"][0]["current_ma"] == approx(50.0)

    def test_missing_current_treated_as_zero(self):
        comps = [{"ref": "LED1", "type": "led"}]
        result = self.pbc.check(comps)
        assert result["total_current_ma"] == 0.0
        assert result["passed"] is True


# ═════════════════════════════════════════════════════════════════════════════
# TraceWidthCalculator
# ═════════════════════════════════════════════════════════════════════════════

class TestTraceWidthCalculator:
    twc = TraceWidthCalculator()

    # ── minimum_width_mm formula ──────────────────────────────────────────────

    def test_zero_current_returns_zero(self):
        assert TraceWidthCalculator.minimum_width_mm(0.0) == 0.0

    def test_negative_current_returns_zero(self):
        assert TraceWidthCalculator.minimum_width_mm(-1.0) == 0.0

    def test_1a_external_1oz_10c_reasonable(self):
        # IPC-2221 for 1 A, 1 oz, 10 °C rise, external → ~0.27 mm
        width = TraceWidthCalculator.minimum_width_mm(1.0)
        assert 0.20 < width < 0.40, f"Expected ~0.27 mm, got {width}"

    def test_2a_wider_than_1a(self):
        w1 = TraceWidthCalculator.minimum_width_mm(1.0)
        w2 = TraceWidthCalculator.minimum_width_mm(2.0)
        assert w2 > w1

    def test_internal_wider_than_external_same_current(self):
        w_ext = TraceWidthCalculator.minimum_width_mm(1.0, external=True)
        w_int = TraceWidthCalculator.minimum_width_mm(1.0, external=False)
        assert w_int > w_ext  # k is halved → needs wider trace

    def test_higher_temp_rise_narrower(self):
        w10 = TraceWidthCalculator.minimum_width_mm(1.0, temp_rise_c=10.0)
        w30 = TraceWidthCalculator.minimum_width_mm(1.0, temp_rise_c=30.0)
        assert w30 < w10  # higher ΔT allowed → narrower is OK

    def test_heavier_copper_narrower(self):
        w1oz = TraceWidthCalculator.minimum_width_mm(1.0, copper_oz=1.0)
        w2oz = TraceWidthCalculator.minimum_width_mm(1.0, copper_oz=2.0)
        assert w2oz < w1oz  # thicker Cu → same area = narrower width

    def test_formula_result_deterministic(self):
        a = TraceWidthCalculator.minimum_width_mm(0.5, 1.0, 10.0, True)
        b = TraceWidthCalculator.minimum_width_mm(0.5, 1.0, 10.0, True)
        assert a == b

    # ── check() method ────────────────────────────────────────────────────────

    def test_empty_nets(self):
        result = self.twc.check([])
        assert result["passed"] is True
        assert result["nets"] == []
        assert "no nets" in result["detail"].lower()

    def test_single_net_passes_with_wide_trace(self):
        nets = [{"name": "PWR", "current_a": 1.0, "width_mm": 1.5}]
        result = self.twc.check(nets)
        assert result["passed"] is True
        assert result["nets"][0]["passed"] is True
        assert result["nets"][0]["margin_pct"] > 0

    def test_single_net_fails_with_narrow_trace(self):
        # 3 A on a 0.1 mm trace → definitely too narrow
        nets = [{"name": "PWR", "current_a": 3.0, "width_mm": 0.1}]
        result = self.twc.check(nets)
        assert result["passed"] is False
        assert result["nets"][0]["passed"] is False
        assert len(result["issues"]) == 1
        assert "PWR" in result["issues"][0]

    def test_multiple_nets_partial_fail(self):
        nets = [
            {"name": "GND", "current_a": 0.1, "width_mm": 2.0},   # passes
            {"name": "HV_PWR", "current_a": 5.0, "width_mm": 0.1},  # fails
        ]
        result = self.twc.check(nets)
        assert result["passed"] is False
        assert result["nets"][0]["passed"] is True
        assert result["nets"][1]["passed"] is False
        assert len(result["issues"]) == 1

    def test_zero_current_net_always_passes(self):
        nets = [{"name": "SIG", "current_a": 0.0, "width_mm": 0.1}]
        result = self.twc.check(nets)
        assert result["nets"][0]["passed"] is True
        assert result["nets"][0]["min_width_mm"] == 0.0

    def test_internal_layer_requires_more_width(self):
        net_ext = {"name": "NET", "current_a": 1.0, "width_mm": 0.5, "layer": "F.Cu"}
        net_int = {"name": "NET", "current_a": 1.0, "width_mm": 0.5, "layer": "In1.Cu"}
        r_ext = self.twc.check([net_ext])
        r_int = self.twc.check([net_int])
        # Internal layer minimum is larger; the same actual width may pass external but
        # provide less margin on internal
        assert r_int["nets"][0]["min_width_mm"] > r_ext["nets"][0]["min_width_mm"]

    def test_detail_string_all_pass(self):
        nets = [{"name": "SIG", "current_a": 0.1, "width_mm": 0.5}]
        result = self.twc.check(nets)
        assert "meet" in result["detail"].lower() or "adequate" in result["detail"].lower()

    def test_detail_string_fail(self):
        nets = [{"name": "HV", "current_a": 10.0, "width_mm": 0.1}]
        result = self.twc.check(nets)
        assert "below" in result["detail"].lower() or "under" in result["detail"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# ImpedanceCalculator
# ═════════════════════════════════════════════════════════════════════════════

class TestImpedanceCalculator:
    ic = ImpedanceCalculator()

    # ── microstrip_impedance formula ──────────────────────────────────────────

    def test_microstrip_50_ohm_approx(self):
        # w=0.25 mm, h=0.2 mm, er=4.5, t=0.035 → ~50 Ω on FR4
        z = ImpedanceCalculator.microstrip_impedance(
            width_mm=0.25, height_mm=0.2, er=4.5, thickness_mm=0.035
        )
        assert 45 < z < 55, f"Expected ~50 Ω, got {z}"

    def test_microstrip_wider_trace_lower_impedance(self):
        z_narrow = ImpedanceCalculator.microstrip_impedance(0.5, 0.2)
        z_wide = ImpedanceCalculator.microstrip_impedance(2.0, 0.2)
        assert z_narrow > z_wide

    def test_microstrip_higher_er_lower_impedance(self):
        z_fr4 = ImpedanceCalculator.microstrip_impedance(1.0, 0.2, er=4.5)
        z_rog = ImpedanceCalculator.microstrip_impedance(1.0, 0.2, er=3.0)
        assert z_rog > z_fr4  # lower er → higher Z

    def test_microstrip_zero_height_returns_zero(self):
        z = ImpedanceCalculator.microstrip_impedance(1.0, 0.0)
        assert z == 0.0

    def test_microstrip_zero_width_returns_zero(self):
        z = ImpedanceCalculator.microstrip_impedance(0.0, 0.2)
        assert z == 0.0

    # ── stripline_impedance formula ───────────────────────────────────────────

    def test_stripline_returns_positive(self):
        z = ImpedanceCalculator.stripline_impedance(0.5, 1.0, er=4.5)
        assert z > 0

    def test_stripline_wider_trace_lower_impedance(self):
        z_narrow = ImpedanceCalculator.stripline_impedance(0.3, 0.8)
        z_wide = ImpedanceCalculator.stripline_impedance(1.0, 0.8)
        assert z_narrow > z_wide

    # ── differential_microstrip_impedance formula ─────────────────────────────

    def test_differential_100_ohm_approx(self):
        # A typical 100 Ω diff pair on FR4: w≈0.17 mm, h≈0.2 mm, s≈0.17 mm
        z = ImpedanceCalculator.differential_microstrip_impedance(
            width_mm=0.17, height_mm=0.2, spacing_mm=0.17, er=4.5
        )
        # Loose check — geometry-dependent, should be in 80–120 Ω range
        assert 70 < z < 130, f"Expected ~100 Ω diff, got {z}"

    def test_differential_wider_spacing_higher_impedance(self):
        z_close = ImpedanceCalculator.differential_microstrip_impedance(0.5, 0.2, 0.1)
        z_far = ImpedanceCalculator.differential_microstrip_impedance(0.5, 0.2, 1.0)
        assert z_far > z_close  # less coupling → higher Z_diff

    # ── check() method ────────────────────────────────────────────────────────

    def test_empty_nets_no_checks(self):
        result = self.ic.check([])
        assert result["passed"] is True
        assert result["nets"] == []
        assert "no controlled" in result["detail"].lower()

    def test_non_controlled_nets_skipped(self):
        nets = [{"name": "SIG", "width_mm": 0.25}]
        result = self.ic.check(nets)
        assert result["nets"] == []

    def test_controlled_impedance_pass(self):
        # w=0.25 mm, h=0.2 mm, er=4.5, t=0.035 → ~50 Ω on FR4
        nets = [{
            "name": "RF_LINE",
            "is_controlled_impedance": True,
            "width_mm": 0.25,
            "height_mm": 0.2,
            "er": 4.5,
            "thickness_mm": 0.035,
            "target_ohms": 50.0,
            "tolerance_pct": 15.0,
        }]
        result = self.ic.check(nets)
        assert result["passed"] is True
        assert result["nets"][0]["passed"] is True

    def test_controlled_impedance_fail_tight_tolerance(self):
        nets = [{
            "name": "RF_LINE",
            "is_controlled_impedance": True,
            "width_mm": 1.9,
            "height_mm": 0.2,
            "er": 4.5,
            "target_ohms": 75.0,   # will miss by a lot
            "tolerance_pct": 2.0,  # very tight
        }]
        result = self.ic.check(nets)
        assert result["passed"] is False
        assert result["nets"][0]["passed"] is False
        assert len(result["issues"]) == 1

    def test_differential_pair_check(self):
        nets = [{
            "name": "USB_DP",
            "is_differential": True,
            "width_mm": 0.5,
            "height_mm": 0.2,
            "spacing_mm": 0.2,
            "er": 4.5,
            "target_ohms": 90.0,
            "tolerance_pct": 15.0,
        }]
        result = self.ic.check(nets)
        assert len(result["nets"]) == 1
        assert result["nets"][0]["type"] == "differential_microstrip"

    def test_stripline_used_for_internal_layer(self):
        nets = [{
            "name": "CLK",
            "is_controlled_impedance": True,
            "width_mm": 0.3,
            "height_mm": 0.4,
            "layer": "In1.Cu",
            "target_ohms": 50.0,
            "tolerance_pct": 30.0,
        }]
        result = self.ic.check(nets)
        assert result["nets"][0]["type"] == "stripline"

    def test_microstrip_used_for_outer_layer(self):
        nets = [{
            "name": "RF",
            "is_controlled_impedance": True,
            "width_mm": 0.3,
            "height_mm": 0.2,
            "layer": "F.Cu",
            "target_ohms": 50.0,
            "tolerance_pct": 30.0,
        }]
        result = self.ic.check(nets)
        assert result["nets"][0]["type"] == "microstrip"

    def test_detail_all_pass(self):
        nets = [{
            "name": "RF",
            "is_controlled_impedance": True,
            "width_mm": 0.25,
            "height_mm": 0.2,
            "er": 4.5,
            "target_ohms": 50.0,
            "tolerance_pct": 20.0,
        }]
        result = self.ic.check(nets)
        assert result["passed"] is True
        assert "within tolerance" in result["detail"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# SPICEGenerator helpers
# ═════════════════════════════════════════════════════════════════════════════

class TestSPICEHelpers:
    def test_parse_value_float(self):
        assert _parse_value(3.3, 0.0) == pytest.approx(3.3)

    def test_parse_value_int(self):
        assert _parse_value(10, 0.0) == pytest.approx(10.0)

    def test_parse_value_nano(self):
        assert _parse_value("100n", 0.0) == pytest.approx(100e-9)

    def test_parse_value_micro(self):
        assert _parse_value("22u", 0.0) == pytest.approx(22e-6)

    def test_parse_value_milli(self):
        assert _parse_value("470m", 0.0) == pytest.approx(0.47)

    def test_parse_value_kilo(self):
        assert _parse_value("4.7k", 0.0) == pytest.approx(4700.0)

    def test_parse_value_mega(self):
        assert _parse_value("1meg", 0.0) == pytest.approx(1e6)

    def test_parse_value_none_uses_default(self):
        assert _parse_value(None, 5.0) == pytest.approx(5.0)

    def test_parse_value_invalid_uses_default(self):
        assert _parse_value("xyz", 9.9) == pytest.approx(9.9)

    def test_fmt_zero(self):
        assert _fmt(0) == "0"

    def test_fmt_kilo(self):
        result = _fmt(1000)
        assert "k" in result

    def test_fmt_micro(self):
        result = _fmt(22e-6, "F")
        assert "u" in result and "F" in result


# ═════════════════════════════════════════════════════════════════════════════
# SPICEGenerator.generate()
# ═════════════════════════════════════════════════════════════════════════════

class TestSPICEGenerator:
    gen = SPICEGenerator()

    def _check_base(self, netlist: str, circuit_name: str):
        """Common assertions for any generated netlist."""
        assert isinstance(netlist, str)
        assert len(netlist) > 100
        assert ".end" in netlist.lower()
        assert "PCB.AI" in netlist
        assert circuit_name.lower() in netlist.lower()

    def test_ldo_default(self):
        netlist = self.gen.generate("ldo", [], [])
        self._check_base(netlist, "ldo")
        assert "Cout" in netlist
        assert "Rload" in netlist
        assert ".tran" in netlist

    def test_ldo_custom_voltages(self):
        comps = [{"ref": "U1", "type": "ldo", "vin": 5.0, "vout": 3.3}]
        netlist = self.gen.generate("ldo", comps, [])
        assert "3.3" in netlist or "Vout=3.3" in netlist

    def test_buck_default(self):
        netlist = self.gen.generate("buck", [], [])
        self._check_base(netlist, "buck")
        assert "L1" in netlist
        assert "D1" in netlist
        assert ".tran" in netlist

    def test_boost_default(self):
        netlist = self.gen.generate("boost", [], [])
        self._check_base(netlist, "boost")
        assert "L1" in netlist

    def test_rc_filter_default(self):
        netlist = self.gen.generate("rc_filter", [], [])
        self._check_base(netlist, "rc")
        assert "R1" in netlist
        assert "C1" in netlist
        assert ".ac" in netlist

    def test_rc_filter_custom_values(self):
        comps = [
            {"ref": "R1", "type": "resistor", "value": "10k"},
            {"ref": "C1", "type": "capacitor", "value": "1n"},
        ]
        netlist = self.gen.generate("rc_filter", comps, [])
        # fc = 1/(2π × 10k × 1n) ≈ 15.9 kHz — check the comment
        assert "Hz" in netlist or "fc" in netlist.lower()

    def test_lc_filter_default(self):
        netlist = self.gen.generate("lc_filter", [], [])
        self._check_base(netlist, "lc")
        assert "L1" in netlist
        assert "C1" in netlist

    def test_diff_amp_default(self):
        netlist = self.gen.generate("diff_amp", [], [])
        self._check_base(netlist, "diff")
        assert "X1" in netlist
        assert ".tran" in netlist

    def test_diff_amp_gain_in_comment(self):
        comps = [
            {"ref": "R1", "type": "resistor", "value": "10k"},
            {"ref": "R2", "type": "resistor", "value": "10k"},
            {"ref": "Rf", "type": "resistor", "value": "100k"},
            {"ref": "Rg", "type": "resistor", "value": "10k"},
        ]
        netlist = self.gen.generate("diff_amp", comps, [])
        # Gain = 100k/10k = 10
        assert "10.00" in netlist or "Gain" in netlist

    def test_unknown_circuit_type_returns_general(self):
        netlist = self.gen.generate("weird_circuit", [], [])
        assert ".end" in netlist.lower()
        assert "weird_circuit" in netlist.lower()

    def test_general_lists_components(self):
        comps = [
            {"ref": "R1", "type": "resistor", "value": "100"},
            {"ref": "C1", "type": "capacitor", "value": "10u"},
        ]
        netlist = self.gen.generate("general", comps, [])
        assert "R1" in netlist
        assert "C1" in netlist

    def test_all_circuit_types_produce_dot_end(self):
        for ctype in SPICEGenerator.CIRCUIT_TEMPLATES:
            netlist = self.gen.generate(ctype, [], [])
            assert ".end" in netlist.lower(), f"Missing .end for circuit_type={ctype}"

    def test_generate_deterministic(self):
        n1 = self.gen.generate("ldo", [], [])
        n2 = self.gen.generate("ldo", [], [])
        # Netlists are identical except for the timestamp line — strip it
        lines1 = [l for l in n1.splitlines() if "Generated:" not in l]
        lines2 = [l for l in n2.splitlines() if "Generated:" not in l]
        assert lines1 == lines2
