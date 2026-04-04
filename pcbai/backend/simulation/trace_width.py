"""
Trace width calculator (IPC-2221).
Computes minimum trace width per net based on current, copper weight, and temperature rise.
Full implementation in Step 6.
"""

import math
import logging

logger = logging.getLogger("pcbai.simulation.trace_width")


class TraceWidthCalculator:
    """
    IPC-2221 trace width calculator.
    Formula: W = (I / (k * dT^0.44))^(1/0.725) / (thickness_oz * 1.378)
    where k=0.048 (external), 0.024 (internal), dT = temperature rise (°C).
    """

    def check(self, nets: list[dict]) -> dict:
        """
        Check all nets for trace width adequacy.
        TODO (Step 6): Per-net pass/fail table with calculated vs actual widths.
        """
        return {
            "check": "Trace Width (IPC-2221)",
            "passed": True,
            "detail": "Trace width check not yet implemented (Step 6).",
            "nets": [],
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
            current_a: Current in amperes
            copper_oz: Copper weight in oz/ft² (1 oz ≈ 35 µm)
            temp_rise_c: Allowable temperature rise in °C
            external: True for external layers, False for internal

        Returns:
            Minimum trace width in mm
        """
        k = 0.048 if external else 0.024
        thickness_mils = copper_oz * 1.378  # oz/ft² to mils
        area_mils2 = (current_a / (k * (temp_rise_c ** 0.44))) ** (1 / 0.725)
        width_mils = area_mils2 / thickness_mils
        width_mm = width_mils * 0.0254
        return round(width_mm, 4)
