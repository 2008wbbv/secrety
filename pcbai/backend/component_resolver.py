"""
component_resolver.py
---------------------
Resolves underspecified component descriptions to concrete, placeable specs.

Logic flow (mirrors spec section "Component Disambiguation System"):
  1. Parse the raw description to determine component type and value
  2. Check design context for assembly method, density hints, existing packages
  3. If context resolves it → pick, produce one-sentence reasoning, move on
  4. If not → generate a targeted clarification question adapted to expertise level

Returns a ResolvedComponent (concrete) or a ClarifyRequest (needs one answer).

Called by the Claude handler before passing component data to KiCad.
Claude can also call this directly when it needs to resolve a specific component
during the conversation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

ExpertiseLevel = Literal["unknown", "beginner", "expert", "mixed"]


# ── Package tables ────────────────────────────────────────────────────────────

# assembly_method → component_type → preferred package
_ASSEMBLY_DEFAULTS: dict[str, dict[str, str]] = {
    "hand":        {"resistor": "0805", "capacitor": "0805", "inductor": "1210", "led": "0805", "diode": "DO-41", "transistor": "SOT-23"},
    "reflow":      {"resistor": "0603", "capacitor": "0603", "inductor": "0805", "led": "0603", "diode": "SOD-123", "transistor": "SOT-23"},
    "production":  {"resistor": "0402", "capacitor": "0402", "inductor": "0603", "led": "0402", "diode": "SOD-123", "transistor": "SOT-23"},
    "mixed":       {"resistor": "0603", "capacitor": "0603", "inductor": "0805", "led": "0603", "diode": "SOD-123", "transistor": "SOT-23"},
}

# package → footprint library ID in KiCad
_PACKAGE_TO_FOOTPRINT: dict[str, dict[str, str]] = {
    "resistor": {
        "0201": "Resistor_SMD:R_0201_0603Metric",
        "0402": "Resistor_SMD:R_0402_1005Metric",
        "0603": "Resistor_SMD:R_0603_1608Metric",
        "0805": "Resistor_SMD:R_0805_2012Metric",
        "1206": "Resistor_SMD:R_1206_3216Metric",
        "through-hole": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
        "TH": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
    },
    "capacitor": {
        "0201": "Capacitor_SMD:C_0201_0603Metric",
        "0402": "Capacitor_SMD:C_0402_1005Metric",
        "0603": "Capacitor_SMD:C_0603_1608Metric",
        "0805": "Capacitor_SMD:C_0805_2012Metric",
        "1206": "Capacitor_SMD:C_1206_3216Metric",
        "through-hole": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
        "TH": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
    },
    "inductor": {
        "0402": "Inductor_SMD:L_0402_1005Metric",
        "0603": "Inductor_SMD:L_0603_1608Metric",
        "0805": "Inductor_SMD:L_0805_2012Metric",
        "1210": "Inductor_SMD:L_1210_3225Metric",
        "through-hole": "Inductor_THT:L_Axial_L5.3mm_D2.2mm_P10.16mm_Horizontal",
    },
    "led": {
        "0402": "LED_SMD:LED_0402_1005Metric",
        "0603": "LED_SMD:LED_0603_1608Metric",
        "0805": "LED_SMD:LED_0805_2012Metric",
        "through-hole": "LED_THT:LED_D5.0mm",
        "TH": "LED_THT:LED_D5.0mm",
    },
    "diode": {
        "SOD-123": "Diode_SMD:D_SOD-123",
        "SOD-323": "Diode_SMD:D_SOD-323",
        "DO-41": "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
        "through-hole": "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    },
    "transistor": {
        "SOT-23": "Package_TO_SOT_SMD:SOT-23",
        "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
        "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        "TO-92": "Package_TO_SOT_THT:TO-92_Inline",
        "TO-220": "Package_TO_SOT_THT:TO-220-3_Vertical",
        "through-hole": "Package_TO_SOT_THT:TO-92_Inline",
    },
}

# Clarification questions by expertise level
_CLARIFY_QUESTIONS: dict[str, dict[ExpertiseLevel, str]] = {
    "resistor": {
        "beginner": (
            "What size resistor do you want? **0805** is easiest to solder by hand and "
            "I'd recommend it for a first build. **0603** is the common standard. "
            "**0402** is very small and hard to hand-solder. Or I can use a through-hole "
            "resistor if you prefer."
        ),
        "expert": "Package? 0402 / 0603 / 0805 / 1206 / TH",
        "mixed": "What package for this resistor? 0805 (easy hand solder), 0603 (standard), 0402 (dense)?",
        "unknown": "What package for this resistor? 0805 (hand-solderable), 0603 (standard), or 0402?",
    },
    "capacitor": {
        "beginner": (
            "What size capacitor? **0805** is easiest to hand-solder. **0603** is standard. "
            "**0402** is very small. I can also use a through-hole capacitor if you want."
        ),
        "expert": "Package? 0402 / 0603 / 0805 / 1206 / TH",
        "mixed": "Cap package? 0805 (easy solder), 0603 (standard), 0402 (dense)?",
        "unknown": "What package for this capacitor? 0805, 0603, or 0402?",
    },
    "inductor": {
        "beginner": (
            "What size inductor? **0805** is reasonable for most hobby builds. "
            "**0603** is smaller and standard in compact designs."
        ),
        "expert": "Package? 0402 / 0603 / 0805 / 1210 / TH",
        "mixed": "Inductor package? 0603 / 0805 / 1210?",
        "unknown": "What package for this inductor? 0603, 0805, or 1210?",
    },
    "led": {
        "beginner": "What size LED? **0805** is easy to hand-solder. **0603** is standard. Or a 5mm through-hole LED?",
        "expert": "Package? 0402 / 0603 / 0805 / TH",
        "mixed": "LED package? 0603 / 0805 / TH?",
        "unknown": "What LED package? 0603, 0805, or through-hole?",
    },
    "diode": {
        "beginner": "What type of diode package? **Through-hole** (DO-41) is easiest for beginners. **SOD-123** is standard SMD.",
        "expert": "Package? SOD-123 / SOD-323 / DO-41 / TH",
        "mixed": "Diode package? SOD-123 (SMD) or through-hole (DO-41)?",
        "unknown": "Diode package? SOD-123 (SMD standard) or through-hole?",
    },
    "transistor": {
        "beginner": "What type of transistor package? **SOT-23** is the standard small SMD package. **TO-92** is through-hole.",
        "expert": "Package? SOT-23 / SOT-223 / TO-92 / TO-220",
        "mixed": "Transistor package? SOT-23 (SMD) or TO-92 (through-hole)?",
        "unknown": "Transistor package? SOT-23 or through-hole?",
    },
}


# ── Type detection ────────────────────────────────────────────────────────────

_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(resistor|res\b|ohm|Ω)\b', re.I), "resistor"),
    (re.compile(r'\b(capacitor|cap\b|farad|µF|uF|nF|pF)\b', re.I), "capacitor"),
    (re.compile(r'\b(inductor|ind\b|henry|µH|uH|nH|mH|coil|ferrite\s+bead)\b', re.I), "inductor"),
    (re.compile(r'\b(led|light\s+emitting\s+diode)\b', re.I), "led"),
    (re.compile(r'\b(diode|schottky|zener|rectifier)\b', re.I), "diode"),
    (re.compile(r'\b(transistor|mosfet|bjt|jfet|fet|nmos|pmos|npn|pnp)\b', re.I), "transistor"),
]

_PACKAGE_IN_DESC: list[re.Pattern] = [
    re.compile(r'\b(0201|0402|0603|0805|1206|1210|2512)\b'),
    re.compile(r'\b(SOT-?23|SOT-?223|SOD-?123|SOD-?323)\b', re.I),
    re.compile(r'\b(QFN|QFP|DFN|LGA|BGA|TSSOP|SOIC)\b', re.I),
    re.compile(r'\b(DO-?41|DO-?214|TO-?92|TO-?220|TO-?263)\b', re.I),
    re.compile(r'\b(through[-\s]?hole|thru[-\s]?hole|TH\b|DIP\b|PTH\b)\b', re.I),
]


def _detect_type(description: str) -> str | None:
    for pattern, comp_type in _TYPE_PATTERNS:
        if pattern.search(description):
            return comp_type
    return None


def _extract_package(description: str) -> str | None:
    for pattern in _PACKAGE_IN_DESC:
        match = pattern.search(description)
        if match:
            return match.group(0).upper().replace(" ", "-").replace("THROUGH-HOLE", "through-hole").replace("THRU-HOLE", "through-hole")
    if re.search(r'\bthrough[-\s]?hole|TH\b|PTH\b', description, re.I):
        return "through-hole"
    return None


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ResolvedComponent:
    """A fully-specified component ready for placement."""
    description: str
    component_type: str
    value: str
    package: str
    footprint_id: str
    reasoning: str
    requires_clarification: bool = False


@dataclass
class ClarifyRequest:
    """The resolver needs one answer from the user before it can proceed."""
    description: str
    component_type: str
    question: str


# ── Design context ────────────────────────────────────────────────────────────

@dataclass
class DesignContext:
    """What we know about the overall design that informs package choices."""
    assembly_method: str | None = None       # "hand" | "reflow" | "production" | "mixed"
    dominant_package: str | None = None       # Most common package already chosen (e.g. "0402")
    board_density: str | None = None          # "low" | "medium" | "high"
    power_dissipation_mw: float | None = None
    existing_packages: list[str] = field(default_factory=list)

    def infer_assembly_method(self) -> str | None:
        """Infer assembly method from existing packages if not explicitly stated."""
        if self.assembly_method:
            return self.assembly_method
        if not self.existing_packages:
            return None
        # If any 0402 present → likely reflow; mostly 0805 → hand
        if any(p in ("0201", "0402") for p in self.existing_packages):
            return "reflow"
        if all(p in ("0805", "1206", "through-hole", "TH", "DO-41", "TO-92") for p in self.existing_packages):
            return "hand"
        return "reflow"  # default for mixed


# ── Resolver ──────────────────────────────────────────────────────────────────

class ComponentResolver:
    """
    Resolves underspecified component descriptions.

    Usage:
        resolver = ComponentResolver()
        result = resolver.resolve(
            description="220 ohm resistor",
            context=DesignContext(assembly_method="reflow"),
            expertise_level="expert",
        )
        if isinstance(result, ResolvedComponent):
            # use result.footprint_id for KiCad placement
        elif isinstance(result, ClarifyRequest):
            # ask result.question to the user
    """

    def resolve(
        self,
        description: str,
        context: DesignContext | None = None,
        expertise_level: ExpertiseLevel = "unknown",
    ) -> ResolvedComponent | ClarifyRequest:
        ctx = context or DesignContext()
        comp_type = _detect_type(description)

        if comp_type is None:
            # Unknown type — pass through as-is, Claude will handle it
            return ResolvedComponent(
                description=description,
                component_type="unknown",
                value=description,
                package="",
                footprint_id="",
                reasoning="Component type not recognized — Claude will resolve.",
            )

        # 1. Package already in description?
        package = _extract_package(description)
        if package:
            footprint = self._footprint(comp_type, package)
            return ResolvedComponent(
                description=description,
                component_type=comp_type,
                value=self._extract_value(description, comp_type),
                package=package,
                footprint_id=footprint,
                reasoning=f"Package {package} specified explicitly in description.",
            )

        # 2. Assembly method provides a default?
        assembly = ctx.infer_assembly_method()
        if assembly and assembly in _ASSEMBLY_DEFAULTS:
            defaults = _ASSEMBLY_DEFAULTS[assembly]
            if comp_type in defaults:
                package = defaults[comp_type]
                footprint = self._footprint(comp_type, package)
                return ResolvedComponent(
                    description=description,
                    component_type=comp_type,
                    value=self._extract_value(description, comp_type),
                    package=package,
                    footprint_id=footprint,
                    reasoning=(
                        f"Selected {package} based on {assembly} assembly method "
                        f"(inferred from {'explicit setting' if ctx.assembly_method else 'existing component packages'})."
                    ),
                )

        # 3. Dominant package in design?
        if ctx.dominant_package and ctx.dominant_package in self._packages_for(comp_type):
            package = ctx.dominant_package
            footprint = self._footprint(comp_type, package)
            return ResolvedComponent(
                description=description,
                component_type=comp_type,
                value=self._extract_value(description, comp_type),
                package=package,
                footprint_id=footprint,
                reasoning=f"Selected {package} to match dominant package in design.",
            )

        # 4. Power dissipation check (e.g. high-power resistor needs 1206 or TH)
        if ctx.power_dissipation_mw and ctx.power_dissipation_mw > 500 and comp_type == "resistor":
            package = "1206"
            footprint = self._footprint(comp_type, package)
            return ResolvedComponent(
                description=description,
                component_type=comp_type,
                value=self._extract_value(description, comp_type),
                package=package,
                footprint_id=footprint,
                reasoning=f"Selected 1206 because power dissipation {ctx.power_dissipation_mw:.0f}mW exceeds 0805 rating (~125mW).",
            )

        # 5. No context — ask the user
        question = self._clarify_question(comp_type, expertise_level)
        return ClarifyRequest(
            description=description,
            component_type=comp_type,
            question=question,
        )

    def batch_resolve(
        self,
        descriptions: list[str],
        context: DesignContext | None = None,
        expertise_level: ExpertiseLevel = "unknown",
    ) -> tuple[list[ResolvedComponent], list[ClarifyRequest]]:
        """
        Resolve a list of descriptions. Returns (resolved, needs_clarification).
        Caller should ask clarification questions before proceeding with layout.
        """
        resolved = []
        needs_clarification = []
        for desc in descriptions:
            result = self.resolve(desc, context, expertise_level)
            if isinstance(result, ResolvedComponent):
                resolved.append(result)
            else:
                needs_clarification.append(result)
        return resolved, needs_clarification

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _footprint(comp_type: str, package: str) -> str:
        table = _PACKAGE_TO_FOOTPRINT.get(comp_type, {})
        # Normalize package string for lookup
        pkg_key = package.upper().replace(" ", "-")
        fp = table.get(package) or table.get(pkg_key) or table.get(pkg_key.lower())
        return fp or ""

    @staticmethod
    def _packages_for(comp_type: str) -> list[str]:
        return list(_PACKAGE_TO_FOOTPRINT.get(comp_type, {}).keys())

    @staticmethod
    def _clarify_question(comp_type: str, expertise_level: ExpertiseLevel) -> str:
        questions = _CLARIFY_QUESTIONS.get(comp_type, {})
        return (
            questions.get(expertise_level)
            or questions.get("unknown")
            or f"What package for this {comp_type}?"
        )

    @staticmethod
    def _extract_value(description: str, comp_type: str) -> str:
        """Best-effort value extraction from a free-text description."""
        # Resistor: look for ohm values
        if comp_type == "resistor":
            m = re.search(r'(\d+[\.,]?\d*)\s*(k|M|m)?\s*(ohm|Ω|R\b)', description, re.I)
            if m:
                return m.group(0).strip()

        # Capacitor: look for farad values
        if comp_type == "capacitor":
            m = re.search(r'(\d+[\.,]?\d*)\s*(p|n|µ|u|m)?F\b', description, re.I)
            if m:
                return m.group(0).strip()

        # Inductor: henry values
        if comp_type == "inductor":
            m = re.search(r'(\d+[\.,]?\d*)\s*(p|n|µ|u|m)?H\b', description, re.I)
            if m:
                return m.group(0).strip()

        # Fallback: first word(s) that look like a value
        m = re.search(r'(\d+[\.,]?\d*\s*[kKmMµupn]?[ΩΩVRFHA]?\w*)', description)
        if m:
            return m.group(0).strip()

        return description
