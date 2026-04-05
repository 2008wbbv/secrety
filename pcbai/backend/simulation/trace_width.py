"""
Trace width calculator (IPC-2221).
Computes minimum trace width per net based on current, copper weight, and
allowable temperature rise. Reports pass/fail with margin for each net.
"""

import logging

logger = logging.getLogger("pcbai.simulation.trace_width")


def _is_internal_layer(layer: str) -> bool:
    """Return True for KiCad internal copper layer names (In1.Cu, In2.Cu, …)."""
    return layer.startswith("In") and layer.endswith(".Cu")


class TraceWidthCalculator:
    """
    IPC-2221 trace width calculator.

    Formula:
        area_mils² = (I / (k × ΔT^0.44))^(1/0.725)
        W_mils     = area_mils² / thickness_mils
        thickness_mils = copper_oz × 1.378

    where
        k = 0.048  (external layers)
        k = 0.024  (internal layers)
        ΔT = allowable temperature rise (°C)
    """

    def check(self, nets: list[dict]) -> dict:
        """
        Check every net for trace-width adequacy (IPC-2221).

        Each net dict may contain:
            name         (str)   — net name
            current_a    (float) — peak current in amperes
            width_mm     (float) — actual routed trace width in mm
            copper_oz    (float) — copper weight in oz/ft²  (default 1.0)
            temp_rise_c  (float) — allowable temperature rise °C (default 10)
            layer        (str)   — KiCad layer name (default "F.Cu")

        Returns a dict with:
            check, passed, nets (per-net detail), issues, detail
        """
        net_results: list[dict] = []
        all_passed = True

        for net in nets:
            name = net.get("name") or "unnamed"
            current_a = float(net.get("current_a") or 0.0)
            actual_width_mm = float(net.get("width_mm") or 0.25)
            copper_oz = float(net.get("copper_oz") or 1.0)
            temp_rise_c = float(net.get("temp_rise_c") or 10.0)
            layer = net.get("layer") or "F.Cu"
            external = not _is_internal_layer(layer)

            min_width_mm = self.minimum_width_mm(current_a, copper_oz, temp_rise_c, external)
            passed = actual_width_mm >= min_width_mm

            if not passed:
                all_passed = False
                logger.warning(
                    "[TraceWidth] Net '%s': actual %.4f mm < required %.4f mm for %.2f A",
                    name, actual_width_mm, min_width_mm, current_a,
                )

            if min_width_mm > 0:
                margin_pct = round(
                    (actual_width_mm - min_width_mm) / min_width_mm * 100, 1
                )
            else:
                margin_pct = 100.0  # 0 A → any width is fine

            net_results.append({
                "name": name,
                "current_a": current_a,
                "actual_width_mm": actual_width_mm,
                "min_width_mm": min_width_mm,
                "margin_pct": margin_pct,
                "passed": passed,
                "layer": layer,
                "external": external,
            })

        failing = [r for r in net_results if not r["passed"]]
        issues = [
            f"Net '{r['name']}': width {r['actual_width_mm']} mm < "
            f"required {r['min_width_mm']} mm for {r['current_a']} A"
            for r in failing
        ]

        if not net_results:
            detail = "No nets to check"
        elif all_passed:
            detail = f"All {len(net_results)} net(s) meet IPC-2221 trace width requirements"
        else:
            detail = f"{len(failing)} of {len(net_results)} net(s) below minimum width"

        return {
            "check": "Trace Width (IPC-2221)",
            "passed": all_passed,
            "nets": net_results,
            "issues": issues,
            "detail": detail,
        }

    @staticmethod
    def minimum_width_mm(
        current_a: float,
        copper_oz: float = 1.0,
        temp_rise_c: float = 10.0,
        external: bool = True,
    ) -> float:
        """
        Calculate minimum trace width in mm using IPC-2221 formula.

        Args:
            current_a:    Current in amperes
            copper_oz:    Copper weight in oz/ft²  (1 oz ≈ 35 µm / 1.378 mils)
            temp_rise_c:  Allowable temperature rise in °C
            external:     True for external layers, False for internal

        Returns:
            Minimum trace width in mm (rounded to 4 decimal places).
            Returns 0.0 for zero current.
        """
        if current_a <= 0:
            return 0.0
        k = 0.048 if external else 0.024
        thickness_mils = copper_oz * 1.378
        area_mils2 = (current_a / (k * (temp_rise_c ** 0.44))) ** (1 / 0.725)
        width_mils = area_mils2 / thickness_mils
        return round(width_mils * 0.0254, 4)
