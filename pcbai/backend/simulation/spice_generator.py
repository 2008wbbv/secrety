"""
SPICE netlist generator.
Generates LTspice-compatible netlists for common PCB power and signal circuits.

Supported circuit types:
    ldo        — Linear voltage regulator (LDO)
    buck       — Buck (step-down) switching regulator
    boost      — Boost (step-up) switching regulator
    rc_filter  — RC low-pass filter
    lc_filter  — LC low-pass filter
    diff_amp   — Differential amplifier (op-amp based)
    general    — Generic behavioural model from component list
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("pcbai.simulation.spice_generator")

# ── Value parsing ─────────────────────────────────────────────────────────────

_MULTIPLIERS: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
}


def _parse_value(val: str | float | int | None, default: float) -> float:
    """
    Parse a value string (e.g. '100n', '10u', '4.7k', '3.3') into a float.
    Falls back to *default* on any parse failure.
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower().replace("Ω", "").replace("ohm", "").strip()
    for suffix in sorted(_MULTIPLIERS, key=len, reverse=True):
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * _MULTIPLIERS[suffix]
            except ValueError:
                return default
    try:
        return float(s)
    except ValueError:
        return default


def _fmt(value: float, unit: str = "") -> str:
    """Format a float into a compact SPICE-friendly string."""
    abs_v = abs(value)
    if abs_v == 0:
        return f"0{unit}"
    for suffix, mult in sorted(_MULTIPLIERS.items(), key=lambda x: x[1], reverse=True):
        if abs_v >= mult * 0.999:
            scaled = value / mult
            # Avoid ugly trailing zeros
            if scaled == int(scaled):
                return f"{int(scaled)}{suffix}{unit}"
            return f"{scaled:.3g}{suffix}{unit}"
    return f"{value:.6g}{unit}"


def _find_comp(components: list[dict], *types: str) -> dict | None:
    """Return first component whose type matches any of *types* (case-insensitive)."""
    types_lower = {t.lower() for t in types}
    for c in components:
        if (c.get("type") or "").lower() in types_lower:
            return c
    return None


def _header(title: str) -> str:
    return (
        f"* {'='*60}\n"
        f"* PCB.AI — {title}\n"
        f"* Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"* {'='*60}\n"
    )


# ── SPICEGenerator ────────────────────────────────────────────────────────────

class SPICEGenerator:
    CIRCUIT_TEMPLATES = {
        "ldo": "LDO regulator",
        "buck": "Buck (step-down) switching regulator",
        "boost": "Boost (step-up) switching regulator",
        "rc_filter": "RC low-pass filter",
        "lc_filter": "LC low-pass filter",
        "diff_amp": "Differential amplifier",
        "general": "General circuit",
    }

    def generate(
        self,
        circuit_type: str,
        components: list[dict],
        nets: list[dict],
    ) -> str:
        """
        Generate a complete SPICE netlist for the given circuit type.

        Args:
            circuit_type: One of the keys in CIRCUIT_TEMPLATES.
            components:   List of component dicts (ref, type, value, …).
            nets:         List of net dicts (name, …) — used for net naming hints.

        Returns:
            A multi-line SPICE netlist string, LTspice-compatible.
        """
        generator = {
            "ldo": self._gen_ldo,
            "buck": self._gen_buck,
            "boost": self._gen_boost,
            "rc_filter": self._gen_rc_filter,
            "lc_filter": self._gen_lc_filter,
            "diff_amp": self._gen_diff_amp,
        }.get(circuit_type)

        if generator is None:
            return self._gen_general(circuit_type, components, nets)

        logger.info("[SPICE] Generating netlist: circuit_type=%s", circuit_type)
        return generator(components, nets)

    # ── LDO ──────────────────────────────────────────────────────────────────

    def _gen_ldo(self, components: list[dict], nets: list[dict]) -> str:
        cap_in = _find_comp(components, "capacitor", "cap", "cin")
        cap_out = _find_comp(components, "capacitor", "cap", "cout")
        reg = _find_comp(components, "ldo", "regulator", "vreg")
        load = _find_comp(components, "resistor", "load", "rload")

        vin = _parse_value((reg or {}).get("vin") or 5.0, 5.0)
        vout = _parse_value((reg or {}).get("vout") or (reg or {}).get("value") or 3.3, 3.3)
        cin_f = _parse_value((cap_in or {}).get("value") or "10u", 10e-6)
        cout_f = _parse_value((cap_out or {}).get("value") or "10u", 10e-6)
        rload_ohm = _parse_value((load or {}).get("value") or "100", 100.0)
        rdropout = max(0.3, (vin - vout) * 0.06)  # ~6% of headroom

        lines = [
            _header("LDO Regulator"),
            f".param Vin={_fmt(vin)} Vout={_fmt(vout)} Rdropout={_fmt(rdropout)}",
            "",
            "* Power supply",
            f"Vin VIN GND DC {{Vin}}",
            "",
            "* Input bypass",
            f"Cin VIN GND {_fmt(cin_f, 'F')}",
            "",
            "* LDO behavioural model",
            ".subckt LDO_BEH IN OUT GND",
            "  * Dropout resistance",
            "  Rdrop IN MID {Rdropout}",
            "  * Ideal voltage regulation (clamp to Vout)",
            "  Ereg OUT GND MID GND 1",
            "  Vreg_clamp MID 0 DC 0  ; series monitor",
            ".ends LDO_BEH",
            "",
            f"X1 VIN VOUT GND LDO_BEH",
            "",
            "* Output bypass",
            f"Cout VOUT GND {_fmt(cout_f, 'F')}",
            "",
            "* Load",
            f"Rload VOUT GND {_fmt(rload_ohm)}",
            "",
            "* Transient analysis — 10 ms with 100 ns step",
            ".tran 100n 10m",
            ".measure TRAN vout_avg AVG V(VOUT) FROM 5m TO 10m",
            ".measure TRAN vout_ripple PP V(VOUT) FROM 5m TO 10m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── Buck ──────────────────────────────────────────────────────────────────

    def _gen_buck(self, components: list[dict], nets: list[dict]) -> str:
        reg = _find_comp(components, "buck", "regulator", "dcdc")
        ind = _find_comp(components, "inductor", "l")
        cap_out = _find_comp(components, "capacitor", "cap", "cout")
        load = _find_comp(components, "resistor", "load")

        vin = _parse_value((reg or {}).get("vin") or 12.0, 12.0)
        vout = _parse_value((reg or {}).get("vout") or (reg or {}).get("value") or 5.0, 5.0)
        fsw_hz = _parse_value((reg or {}).get("fsw") or "500k", 500e3)
        l_h = _parse_value((ind or {}).get("value") or "22u", 22e-6)
        cout_f = _parse_value((cap_out or {}).get("value") or "100u", 100e-6)
        esr = 0.05  # typical ceramic ESR
        rload_ohm = _parse_value((load or {}).get("value") or "10", 10.0)
        duty = min(0.95, max(0.05, vout / vin))

        lines = [
            _header("Buck (Step-Down) Switching Regulator"),
            f".param Vin={_fmt(vin)} Vout={_fmt(vout)} Fsw={_fmt(fsw_hz)}",
            f".param L={_fmt(l_h, 'H')} Cout={_fmt(cout_f, 'F')} Duty={duty:.3f}",
            "",
            "* Input supply",
            f"Vin VIN GND DC {{Vin}}",
            "Cin VIN GND 100uF",
            "",
            "* Ideal switch (PWM)",
            "Asw VIN SW 0 0 SW_MODEL",
            ".model SW_MODEL SW(Ron=10m Roff=1Meg Von=0.5 Voff=0.4)",
            "Vpwm PG 0 PULSE(0 1 0 1n 1n {Duty/Fsw} {1/Fsw})",
            "Bgate SW_CTRL 0 V=(V(PG)>0.5 ? 1 : 0)",
            "",
            "* Freewheeling diode",
            "D1 GND SW D_IDEAL",
            ".model D_IDEAL D(Ron=0.01 Roff=1Meg Vfwd=0.5)",
            "",
            "* Output filter",
            f"L1 SW_NODE LOUT {_fmt(l_h, 'H')}",
            f"Resr LOUT OUT {esr}",
            f"Cout OUT GND {_fmt(cout_f, 'F')}",
            "",
            "* Load",
            f"Rload OUT GND {_fmt(rload_ohm)}",
            "",
            "* Initial conditions",
            f".IC V(OUT)={vout}",
            "",
            "* Transient — 5 ms startup",
            ".tran 100n 5m",
            ".measure TRAN vout_avg AVG V(OUT) FROM 2m TO 5m",
            ".measure TRAN vout_ripple PP V(OUT) FROM 2m TO 5m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── Boost ─────────────────────────────────────────────────────────────────

    def _gen_boost(self, components: list[dict], nets: list[dict]) -> str:
        reg = _find_comp(components, "boost", "regulator", "dcdc")
        ind = _find_comp(components, "inductor", "l")
        cap_out = _find_comp(components, "capacitor", "cap", "cout")
        load = _find_comp(components, "resistor", "load")

        vin = _parse_value((reg or {}).get("vin") or 3.3, 3.3)
        vout = _parse_value((reg or {}).get("vout") or (reg or {}).get("value") or 5.0, 5.0)
        fsw_hz = _parse_value((reg or {}).get("fsw") or "500k", 500e3)
        l_h = _parse_value((ind or {}).get("value") or "10u", 10e-6)
        cout_f = _parse_value((cap_out or {}).get("value") or "47u", 47e-6)
        rload_ohm = _parse_value((load or {}).get("value") or "50", 50.0)
        duty = min(0.90, max(0.05, 1 - vin / vout))

        lines = [
            _header("Boost (Step-Up) Switching Regulator"),
            f".param Vin={_fmt(vin)} Vout={_fmt(vout)} Fsw={_fmt(fsw_hz)}",
            f".param L={_fmt(l_h, 'H')} Cout={_fmt(cout_f, 'F')} Duty={duty:.3f}",
            "",
            "* Input supply",
            f"Vin VIN GND DC {{Vin}}",
            "Cin VIN GND 22uF",
            "",
            "* Boost inductor",
            f"L1 VIN LSW {_fmt(l_h, 'H')}",
            "",
            "* Low-side switch",
            "Asw LSW GND 0 0 SW_MODEL",
            ".model SW_MODEL SW(Ron=50m Roff=1Meg Von=0.5 Voff=0.4)",
            "Vpwm PG 0 PULSE(0 1 0 1n 1n {Duty/Fsw} {1/Fsw})",
            "",
            "* Output diode",
            "D1 LSW OUT D_SCHOTTKY",
            ".model D_SCHOTTKY D(Ron=0.02 Roff=1Meg Vfwd=0.3)",
            "",
            "* Output capacitor",
            f"Cout OUT GND {_fmt(cout_f, 'F')}",
            "",
            "* Load",
            f"Rload OUT GND {_fmt(rload_ohm)}",
            "",
            ".IC V(OUT)={vout}",
            ".tran 100n 5m",
            ".measure TRAN vout_avg AVG V(OUT) FROM 2m TO 5m",
            ".measure TRAN vout_ripple PP V(OUT) FROM 2m TO 5m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── RC filter ─────────────────────────────────────────────────────────────

    def _gen_rc_filter(self, components: list[dict], nets: list[dict]) -> str:
        r_comp = _find_comp(components, "resistor", "r")
        c_comp = _find_comp(components, "capacitor", "cap", "c")

        r_ohm = _parse_value((r_comp or {}).get("value") or "1k", 1e3)
        c_f = _parse_value((c_comp or {}).get("value") or "100n", 100e-9)
        fc_hz = 1 / (2 * 3.14159 * r_ohm * c_f)
        sim_freq = max(fc_hz * 100, 1e6)  # AC sweep to 100× fc

        lines = [
            _header("RC Low-Pass Filter"),
            f"* Cutoff frequency: {_fmt(fc_hz, 'Hz')}",
            f".param R={_fmt(r_ohm)} C={_fmt(c_f, 'F')}",
            "",
            "* Source (1 Vpp AC for AC analysis)",
            "Vin IN GND AC 1",
            "",
            "* Filter",
            f"R1 IN OUT {{R}}",
            f"C1 OUT GND {{C}}",
            "",
            "* AC sweep: 10 Hz to 100× fc",
            f".ac dec 100 10 {_fmt(sim_freq)}",
            ".measure AC fc WHEN V(OUT)=0.707",
            "",
            "* Step response",
            "Vstep IN GND PULSE(0 1 1u 1n 1n 1m 2m)",
            ".tran 10n 3m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── LC filter ─────────────────────────────────────────────────────────────

    def _gen_lc_filter(self, components: list[dict], nets: list[dict]) -> str:
        l_comp = _find_comp(components, "inductor", "l")
        c_comp = _find_comp(components, "capacitor", "cap", "c")
        load = _find_comp(components, "resistor", "load")

        l_h = _parse_value((l_comp or {}).get("value") or "10u", 10e-6)
        c_f = _parse_value((c_comp or {}).get("value") or "10u", 10e-6)
        rload_ohm = _parse_value((load or {}).get("value") or "10", 10.0)
        rl_ohm = 0.05  # inductor DCR
        fc_hz = 1 / (2 * 3.14159 * (l_h * c_f) ** 0.5)
        sim_freq = max(fc_hz * 200, 1e6)

        lines = [
            _header("LC Low-Pass Filter"),
            f"* Resonant frequency: {_fmt(fc_hz, 'Hz')}",
            f".param L={_fmt(l_h, 'H')} C={_fmt(c_f, 'F')}",
            "",
            "Vin IN GND AC 1",
            "",
            f"L1 IN MID {{L}} Rser={rl_ohm}",
            f"C1 MID GND {{C}}",
            f"Rload MID GND {_fmt(rload_ohm)}",
            "",
            f".ac dec 100 10 {_fmt(sim_freq)}",
            ".measure AC fc WHEN V(MID)=0.707",
            "",
            "Vstep IN GND PULSE(0 5 1u 1n 1n 1m 2m)",
            ".tran 100n 3m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── Differential amplifier ────────────────────────────────────────────────

    def _gen_diff_amp(self, components: list[dict], nets: list[dict]) -> str:
        r_comps = [c for c in components if (c.get("type") or "").lower() in ("resistor", "r")]
        opamp = _find_comp(components, "opamp", "op-amp", "opamp", "opa")

        r1 = _parse_value((r_comps[0]["value"] if len(r_comps) > 0 else None) or "10k", 10e3)
        r2 = _parse_value((r_comps[1]["value"] if len(r_comps) > 1 else None) or "10k", 10e3)
        rf = _parse_value((r_comps[2]["value"] if len(r_comps) > 2 else None) or "10k", 10e3)
        rg = _parse_value((r_comps[3]["value"] if len(r_comps) > 3 else None) or "10k", 10e3)
        gain = rf / rg
        vsupply = _parse_value((opamp or {}).get("vsupply") or 15.0, 15.0)

        lines = [
            _header("Differential Amplifier (Op-Amp)"),
            f"* Gain = Rf/Rg = {_fmt(rf)}/{_fmt(rg)} = {gain:.2f}",
            f".param R1={_fmt(r1)} R2={_fmt(r2)} Rf={_fmt(rf)} Rg={_fmt(rg)}",
            "",
            "* Power supplies",
            f"Vcc VCC GND DC {_fmt(vsupply)}",
            f"Vee VEE GND DC -{_fmt(vsupply)}",
            "",
            "* Input signals",
            "Vp INP GND SIN(0 1 1k)",
            "Vn INN GND SIN(0 0.5 1k)",
            "",
            "* Input dividers",
            "R1 INP V1 {R1}",
            "R2 V1 GND {R2}",
            "R3 INN V2 {R1}",
            "R4 V2 GND {R2}",
            "",
            "* Feedback",
            "Rf VOUT INM {Rf}",
            "Rg V2 INP_OP {Rg}",
            "",
            "* Ideal op-amp behavioural model",
            ".subckt OPAMP_BEH INP INN OUT VCC VEE",
            "  Eamp OUT 0 INP INN 100k",
            "  Rout OUT 0 1",
            ".ends OPAMP_BEH",
            "",
            "X1 INP_OP INM VOUT VCC VEE OPAMP_BEH",
            "",
            ".tran 1u 5m",
            ".measure TRAN vout_pp PP V(VOUT) FROM 1m TO 5m",
            ".end",
        ]
        return "\n".join(lines) + "\n"

    # ── General fallback ──────────────────────────────────────────────────────

    def _gen_general(
        self, circuit_type: str, components: list[dict], nets: list[dict]
    ) -> str:
        """Generate a basic netlist from whatever components are provided."""
        lines = [
            _header(f"General Circuit — {circuit_type}"),
            "* Component list:",
        ]
        for i, comp in enumerate(components):
            ref = comp.get("ref") or f"X{i+1}"
            ctype = comp.get("type") or "unknown"
            val = comp.get("value") or ""
            lines.append(f"* {ref} ({ctype}) = {val}")

        if not components:
            lines.append("* (no components provided)")

        lines += [
            "",
            "* Net list:",
        ]
        for net in nets:
            lines.append(f"* {net.get('name', 'unnamed')}")

        lines += ["", ".end"]
        return "\n".join(lines) + "\n"
