"""
Impedance calculator.
Computes trace impedance for controlled impedance nets and differential pairs.
Full implementation in Step 6.
"""

import math
import logging

logger = logging.getLogger("pcbai.simulation.impedance")


class ImpedanceCalculator:
    def check(self, nets: list[dict]) -> dict:
        """
        Check controlled impedance and differential pair nets.
        TODO (Step 6): Per-net calculated vs target impedance, pass/fail.
        """
        return {
            "check": "Impedance",
            "passed": True,
            "detail": "Impedance check not yet implemented (Step 6).",
            "nets": [],
        }

    @staticmethod
    def microstrip_impedance(
        width_mm: float,
        height_mm: float,
        er: float = 4.5,
        thickness_mm: float = 0.035,
    ) -> float:
        """
        Calculate characteristic impedance of a microstrip trace (Ω).
        Uses the IPC-2141A formula.

        Args:
            width_mm: Trace width in mm
            height_mm: Dielectric height in mm
            er: Relative dielectric constant (FR4 ≈ 4.5)
            thickness_mm: Trace thickness in mm (1 oz Cu ≈ 0.035 mm)

        Returns:
            Characteristic impedance in ohms
        """
        w = width_mm
        h = height_mm
        t = thickness_mm
        # Effective width correction
        w_eff = w + (t / math.pi) * (1 + math.log(2 * h / t))
        # Hammerstad-Jensen approximation
        if w_eff / h < 1:
            z0 = (60 / math.sqrt(er)) * math.log(8 * h / w_eff + w_eff / (4 * h))
        else:
            z0 = (120 * math.pi / math.sqrt(er)) / (w_eff / h + 1.393 + 0.667 * math.log(w_eff / h + 1.444))
        return round(z0, 2)
