"""
Impedance calculator.
Checks controlled-impedance nets and differential pairs using IPC-2141A /
Hammerstad-Jensen microstrip and stripline approximations.
"""

import math
import logging

logger = logging.getLogger("pcbai.simulation.impedance")


def _is_internal_layer(layer: str) -> bool:
    return layer.startswith("In") and layer.endswith(".Cu")


class ImpedanceCalculator:
    """
    Controlled-impedance and differential-pair checker.

    Supported geometries
    --------------------
    microstrip   — single-ended trace on outer copper layer
    stripline    — single-ended trace on inner copper layer
    differential — edge-coupled microstrip differential pair

    Net dicts processed by check() may include:
        name                  (str)   — net name
        is_controlled_impedance (bool)
        is_differential       (bool)
        width_mm              (float) — trace width in mm
        height_mm             (float) — dielectric height (core/prepreg) in mm
        spacing_mm            (float) — edge-to-edge gap for differential pairs
        er                    (float) — relative permittivity (default 4.5 for FR4)
        thickness_mm          (float) — copper trace thickness in mm (default 0.035)
        target_ohms           (float) — impedance target in Ω (default 50)
        tolerance_pct         (float) — allowed ±% deviation (default 10)
        layer                 (str)   — KiCad layer name
    """

    def check(self, nets: list[dict]) -> dict:
        """
        Check controlled-impedance nets and differential pairs.

        Returns a dict with:
            check, passed, nets (per-net detail), issues, detail
        """
        net_results: list[dict] = []
        all_passed = True

        for net in nets:
            is_controlled = net.get("is_controlled_impedance", False)
            is_differential = net.get("is_differential", False)

            if not is_controlled and not is_differential:
                continue

            name = net.get("name") or "unnamed"
            width_mm = float(net.get("width_mm") or 0.25)
            height_mm = float(net.get("height_mm") or 0.2)
            er = float(net.get("er") or 4.5)
            thickness_mm = float(net.get("thickness_mm") or 0.035)
            target_ohms = float(net.get("target_ohms") or 50.0)
            tolerance_pct = float(net.get("tolerance_pct") or 10.0)
            layer = net.get("layer") or "F.Cu"

            if is_differential:
                spacing_mm = float(net.get("spacing_mm") or 0.2)
                calculated_ohms = self.differential_microstrip_impedance(
                    width_mm, height_mm, spacing_mm, er, thickness_mm
                )
                check_type = "differential_microstrip"
            elif _is_internal_layer(layer):
                calculated_ohms = self.stripline_impedance(
                    width_mm, height_mm, er, thickness_mm
                )
                check_type = "stripline"
            else:
                calculated_ohms = self.microstrip_impedance(
                    width_mm, height_mm, er, thickness_mm
                )
                check_type = "microstrip"

            error_pct = abs(calculated_ohms - target_ohms) / target_ohms * 100
            passed = error_pct <= tolerance_pct

            if not passed:
                all_passed = False
                logger.warning(
                    "[Impedance] Net '%s': %.1f Ω vs target %.1f Ω (%.1f%% error)",
                    name, calculated_ohms, target_ohms, error_pct,
                )

            result: dict = {
                "name": name,
                "type": check_type,
                "target_ohms": target_ohms,
                "calculated_ohms": calculated_ohms,
                "error_pct": round(error_pct, 1),
                "tolerance_pct": tolerance_pct,
                "passed": passed,
                "width_mm": width_mm,
                "height_mm": height_mm,
            }
            if is_differential:
                result["spacing_mm"] = float(net.get("spacing_mm") or 0.2)
            net_results.append(result)

        failing = [r for r in net_results if not r["passed"]]
        issues = [
            f"Net '{r['name']}': {r['calculated_ohms']} Ω vs target "
            f"{r['target_ohms']} Ω ({r['error_pct']}% error, "
            f"tolerance ±{r['tolerance_pct']}%)"
            for r in failing
        ]

        if not net_results:
            detail = "No controlled-impedance nets to check"
        elif all_passed:
            detail = (
                f"All {len(net_results)} controlled-impedance net(s) within tolerance"
            )
        else:
            detail = f"{len(failing)} of {len(net_results)} net(s) outside impedance tolerance"

        return {
            "check": "Impedance",
            "passed": all_passed,
            "nets": net_results,
            "issues": issues,
            "detail": detail,
        }

    # ── Impedance formulae ────────────────────────────────────────────────────

    @staticmethod
    def microstrip_impedance(
        width_mm: float,
        height_mm: float,
        er: float = 4.5,
        thickness_mm: float = 0.035,
    ) -> float:
        """
        Characteristic impedance of a microstrip trace (Ω).
        IPC-2141A / Hammerstad-Jensen approximation.

        Args:
            width_mm:     Trace width in mm
            height_mm:    Dielectric height in mm
            er:           Relative permittivity of substrate (FR4 ≈ 4.5)
            thickness_mm: Copper trace thickness in mm (1 oz ≈ 0.035 mm)

        Returns:
            Characteristic impedance in ohms.
        """
        w = width_mm
        h = height_mm
        t = thickness_mm

        if h <= 0 or w <= 0:
            return 0.0

        # Effective width correction for trace thickness
        if t > 0 and h > 0:
            w_eff = w + (t / math.pi) * (1 + math.log(2 * h / t))
        else:
            w_eff = w

        if w_eff / h < 1:
            z0 = (60 / math.sqrt(er)) * math.log(8 * h / w_eff + w_eff / (4 * h))
        else:
            z0 = (
                (120 * math.pi / math.sqrt(er))
                / (w_eff / h + 1.393 + 0.667 * math.log(w_eff / h + 1.444))
            )
        return round(z0, 2)

    @staticmethod
    def stripline_impedance(
        width_mm: float,
        height_mm: float,
        er: float = 4.5,
        thickness_mm: float = 0.035,
    ) -> float:
        """
        Characteristic impedance of a centered stripline trace (Ω).
        Uses the IPC-2141A approximation for a trace centered between two
        reference planes.

        Args:
            width_mm:     Trace width in mm
            height_mm:    Total dielectric thickness (between reference planes) in mm
            er:           Relative permittivity of substrate
            thickness_mm: Copper trace thickness in mm

        Returns:
            Characteristic impedance in ohms.
        """
        w = width_mm
        b = height_mm   # total board thickness between planes
        t = thickness_mm

        if b <= 0 or w <= 0:
            return 0.0

        # Effective width for thickness correction
        if t > 0:
            w_eff = w + (t / math.pi) * (1 + math.log(4 * math.e * b / t))
        else:
            w_eff = w

        z0 = (60 / math.sqrt(er)) * math.log(4 * b / (0.67 * math.pi * (0.8 * w_eff + t)))
        return round(max(z0, 0.0), 2)

    @staticmethod
    def differential_microstrip_impedance(
        width_mm: float,
        height_mm: float,
        spacing_mm: float,
        er: float = 4.5,
        thickness_mm: float = 0.035,
    ) -> float:
        """
        Differential impedance of an edge-coupled microstrip pair (Ω).
        Uses the odd-mode impedance approximation:
            Z_diff ≈ 2 × Z0_single × (1 - 0.347 × exp(-2.9 × s/h))

        Args:
            width_mm:     Trace width in mm
            height_mm:    Dielectric height in mm
            spacing_mm:   Edge-to-edge gap between traces in mm
            er:           Relative permittivity
            thickness_mm: Trace thickness in mm

        Returns:
            Differential impedance in ohms.
        """
        z0_single = ImpedanceCalculator.microstrip_impedance(
            width_mm, height_mm, er, thickness_mm
        )
        h = height_mm
        s = spacing_mm

        if h <= 0:
            return round(2 * z0_single, 2)

        # Odd-mode coupling correction
        coupling_factor = 1 - 0.347 * math.exp(-2.9 * s / h)
        z_diff = 2 * z0_single * coupling_factor
        return round(z_diff, 2)
