"""
Power budget calculator.
Sums component current draws, checks regulator capacity margin, and flags
high-dissipation components that may need thermal management.
"""

import logging

logger = logging.getLogger("pcbai.simulation.power_budget")

_REGULATOR_TYPES = {"regulator", "ldo", "vreg", "buck", "boost", "pmic", "dcdc"}


class PowerBudgetCalculator:
    MARGIN_THRESHOLD = 0.20      # Flag if available margin < 20%
    THERMAL_WARNING_MW = 500.0   # Flag components dissipating > 500 mW

    def check(self, components: list[dict]) -> dict:
        """
        Calculate power budget from a list of component dicts.

        Each component may contain:
            ref          (str)   — reference designator, e.g. "U1"
            type         (str)   — "resistor", "ldo", "mcu", etc.
            value        (str)   — component value string (informational)
            current_ma   (float) — quiescent / operating current draw in mA
            voltage_v    (float) — supply voltage; used to compute power if power_mw absent
            power_mw     (float) — explicit power dissipation override in mW
            is_regulator (bool)  — True to treat this component as a power source
            capacity_ma  (float) — maximum output current for regulators in mA

        Returns a dict with:
            check, passed, total_current_ma, total_power_mw,
            regulator_capacity_ma, margin_pct, components (per-component detail),
            thermal_warnings, issues, detail
        """
        regulators: list[dict] = []
        loads: list[dict] = []

        for comp in components:
            comp_type = (comp.get("type") or "").lower().strip()
            if comp.get("is_regulator") or comp_type in _REGULATOR_TYPES:
                regulators.append(comp)
            else:
                loads.append(comp)

        # ── Aggregate load ────────────────────────────────────────────────────
        total_current_ma = 0.0
        total_power_mw = 0.0
        component_details: list[dict] = []
        thermal_warnings: list[str] = []

        for comp in loads:
            current_ma = float(comp.get("current_ma") or 0.0)
            voltage_v = float(comp.get("voltage_v") or 3.3)
            # Use explicit power if given, else V×I
            power_mw = float(comp.get("power_mw") or (current_ma * voltage_v))

            total_current_ma += current_ma
            total_power_mw += power_mw

            ref = comp.get("ref") or "?"
            component_details.append({
                "ref": ref,
                "type": comp.get("type") or "unknown",
                "current_ma": round(current_ma, 3),
                "power_mw": round(power_mw, 3),
            })

            if power_mw > self.THERMAL_WARNING_MW:
                thermal_warnings.append(
                    f"{ref}: {power_mw:.0f} mW (exceeds {self.THERMAL_WARNING_MW:.0f} mW threshold)"
                )
                logger.warning("[PowerBudget] High dissipation — %s", thermal_warnings[-1])

        total_current_ma = round(total_current_ma, 3)
        total_power_mw = round(total_power_mw, 3)

        # ── Regulator margin ──────────────────────────────────────────────────
        issues: list[str] = []
        passed = True
        total_capacity_ma: float | None = None
        margin_pct: float | None = None

        if regulators:
            total_capacity_ma = sum(
                float(r.get("capacity_ma") or 500.0) for r in regulators
            )
            if total_capacity_ma > 0:
                margin = (total_capacity_ma - total_current_ma) / total_capacity_ma
            else:
                margin = 1.0
            margin_pct = round(margin * 100, 1)

            if margin < self.MARGIN_THRESHOLD:
                passed = False
                issues.append(
                    f"Regulator margin {margin_pct}% < {self.MARGIN_THRESHOLD*100:.0f}% "
                    f"(load={total_current_ma:.1f} mA, capacity={total_capacity_ma:.1f} mA)"
                )
                logger.warning("[PowerBudget] Under-margin: %s", issues[-1])

        for w in thermal_warnings:
            issues.append(f"Thermal: {w}")

        # ── Build summary detail string ────────────────────────────────────────
        if issues:
            detail = "; ".join(issues)
        elif margin_pct is not None:
            detail = (
                f"OK — {total_current_ma:.1f} mA total load, "
                f"{total_capacity_ma:.1f} mA capacity, "
                f"{margin_pct:.1f}% margin"
            )
        else:
            detail = f"OK — {total_current_ma:.1f} mA total (no regulator specified)"

        return {
            "check": "Power Budget",
            "passed": passed,
            "total_current_ma": total_current_ma,
            "total_power_mw": total_power_mw,
            "regulator_capacity_ma": total_capacity_ma,
            "margin_pct": margin_pct,
            "components": component_details,
            "thermal_warnings": thermal_warnings,
            "issues": issues,
            "detail": detail,
        }
