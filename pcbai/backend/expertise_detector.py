"""
expertise_detector.py
---------------------
Rule-based expertise detector. Analyzes user message text and produces
a scored estimate of the user's PCB knowledge level.

Design:
  - Runs locally on every user message (fast, no API call needed)
  - Gives Claude a pre-populated best-guess in the system prompt
  - Claude then refines via _meta block in its response
  - Two passes together converge quickly (usually 1-2 messages)

Levels: "unknown" | "beginner" | "expert" | "mixed"

"mixed" means expert signals in one domain but beginner signals in another.
The session tracks per-domain scores so the system prompt can say
"user is expert in power design but beginner in RF."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

ExpertiseLevel = Literal["unknown", "beginner", "expert", "mixed"]


# ── Signal tables ─────────────────────────────────────────────────────────────

# (pattern, weight, domain)
_EXPERT_SIGNALS: list[tuple[re.Pattern, float, str]] = [
    # Schematic / layout terminology
    (re.compile(r'\b(impedance|characteristic impedance|differential pair|diff pair)\b', re.I), 2.0, "signal_integrity"),
    (re.compile(r'\b(net\s?class|netclass|stackup|layer\s?stack)\b', re.I), 2.0, "layout"),
    (re.compile(r'\b(via\s?stitch(?:ing)?|thermal\s?relief|copper\s?pour|plane)\b', re.I), 1.5, "layout"),
    (re.compile(r'\b(keepout|courtyard|silkscreen|fab(?:rication)?\s?layer)\b', re.I), 1.5, "layout"),
    (re.compile(r'\b(gerber|excellon|drill\s?file|pick\s?and\s?place|centroid)\b', re.I), 1.5, "fabrication"),
    (re.compile(r'\b(DRC|ERC|netlist|schematic\s?capture|footprint|land\s?pattern)\b', re.I), 1.5, "eda"),
    (re.compile(r'\b(decoupling|bypass\s?cap(?:acitor)?|bulk\s?capacitance)\b', re.I), 1.5, "power"),
    (re.compile(r'\b(LDO|switching\s?regulator|buck|boost|SMPS|PWM|duty\s?cycle)\b', re.I), 1.5, "power"),
    (re.compile(r'\b(EMC|EMI|ESD|RF\s?shielding|ground\s?plane|return\s?path)\b', re.I), 2.0, "signal_integrity"),
    (re.compile(r'\b(controlled\s?impedance|50\s?[Ωohm]|75\s?[Ωohm]|100\s?[Ωohm])\b', re.I), 2.0, "signal_integrity"),
    (re.compile(r'\b(SPI|I2C|UART|CAN\s?bus|USB|LVDS|MIPI|PCIe|DDR)\b', re.I), 1.0, "protocols"),
    (re.compile(r'\b(thermal\s?pad|exposed\s?pad|heatsink|thermal\s?via)\b', re.I), 1.5, "thermal"),
    (re.compile(r'\b(length\s?match(?:ing)?|skew|propagation\s?delay)\b', re.I), 2.0, "signal_integrity"),

    # Package designators (very strong expert signal)
    (re.compile(r'\b(0201|0402|0603|0805|1206|1210|2512)\b'), 2.5, "components"),
    (re.compile(r'\b(SOT-?23|SOT-?223|SOT-?363|SOT-?563)\b', re.I), 2.5, "components"),
    (re.compile(r'\b(QFN|QFP|DFN|LGA|BGA|VQFN|MLF|SON)\b', re.I), 2.5, "components"),
    (re.compile(r'\b(TSSOP|SOIC|SOP|MSOP|SSOP|TSOP|DIP|SIP)\b', re.I), 2.0, "components"),
    (re.compile(r'\b(TO-?92|TO-?220|TO-?263|DO-?214|DO-?41)\b', re.I), 2.0, "components"),

    # Standards (extremely strong expert signal)
    (re.compile(r'\b(IPC-?2221|IPC-?2141|IPC-?7351|IPC-?6012)\b', re.I), 3.0, "standards"),
    (re.compile(r'\b(MIL-?STD|JEDEC|J-?STD|IEC\s?\d+|UL\s?\d+)\b', re.I), 3.0, "standards"),
    (re.compile(r'\b(IPC|JLCPCB\s?rule|fab\s?tolerance|min(?:imum)?\s?trace)\b', re.I), 1.5, "fabrication"),

    # IC part numbers (heuristic: 2+ uppercase letters + 3+ digits, optionally more chars)
    (re.compile(r'\b[A-Z]{2,5}\d{3,}[A-Z0-9\-]*\b'), 2.0, "components"),

    # Precise electrical specs with units
    (re.compile(r'\b\d+(\.\d+)?\s*(mA|µA|uA|nA|A)\b', re.I), 1.0, "power"),
    (re.compile(r'\b\d+(\.\d+)?\s*(mV|µV|uV|kV)\b', re.I), 1.0, "power"),
    (re.compile(r'\b\d+(\.\d+)?\s*(MHz|GHz|kHz)\b', re.I), 1.5, "signal_integrity"),
    (re.compile(r'\b\d+(\.\d+)?\s*(nH|µH|uH|mH)\b', re.I), 1.0, "components"),
    (re.compile(r'\b\d+(\.\d+)?\s*(pF|nF|µF|uF)\b', re.I), 1.0, "components"),
    (re.compile(r'\b\d+(\.\d+)?\s*(mΩ|mOhm|kΩ|kOhm|MΩ|MOhm)\b', re.I), 1.0, "components"),
    (re.compile(r'\b\d+(\.\d+)?\s*(mm|mil|thou)\s*(trace|via|clearance|width)\b', re.I), 1.5, "layout"),

    # Layer references
    (re.compile(r'\b(F\.Cu|B\.Cu|In\d+\.Cu|front\s?copper|back\s?copper|inner\s?layer)\b', re.I), 1.5, "layout"),
    (re.compile(r'\b(\d+-?layer|4-?layer|6-?layer|8-?layer)\b', re.I), 1.5, "layout"),
    (re.compile(r'\b(1\s?oz|2\s?oz|0\.5\s?oz)\s*(copper|cu)\b', re.I), 2.0, "layout"),

    # Fab-specific references
    (re.compile(r'\b(JLCPCB|PCBWay|OSHPark|Eurocircuits|Würth|Altium|KiCad|Eagle|Orcad)\b', re.I), 1.0, "eda"),
    (re.compile(r'\b(HASL|ENIG|OSP|hard\s?gold|immersion\s?(silver|tin))\b', re.I), 2.0, "fabrication"),
]

_BEGINNER_SIGNALS: list[tuple[re.Pattern, float, str]] = [
    # Describing function, not parts
    (re.compile(r'\b(something\s+that|a\s+thing\s+that|device\s+that|circuit\s+that)\b', re.I), 1.5, "general"),
    (re.compile(r'\b(make\s+it|make\s+the|want\s+it\s+to|needs?\s+to\s+be\s+able\s+to)\b', re.I), 1.0, "general"),
    (re.compile(r'\b(turns?\s+on|lights?\s+up|blinks?|flashes?|beeps?|spins?|moves?|rotates?)\b', re.I), 0.8, "general"),

    # Consumer/app language
    (re.compile(r'\b(connect\s+to\s+my\s+phone|phone\s+app|smartphone|tablet|alexa|siri)\b', re.I), 2.0, "general"),
    (re.compile(r'\b(just\s+needs?\s+to|simply|basically|kind\s+of\s+like)\b', re.I), 0.8, "general"),
    (re.compile(r'\b(I\s+don\'t\s+know|not\s+sure|I\s+think|maybe|probably|I\s+guess)\b', re.I), 1.0, "general"),

    # Asking what things are
    (re.compile(r'\b(what\s+is\s+a?n?\s+|what\s+are\s+|what\s+does\s+|how\s+do\s+I)\b', re.I), 2.0, "general"),
    (re.compile(r'\b(can\s+you\s+explain|I\s+don\'t\s+understand|I\'m\s+new|first\s+time|beginner)\b', re.I), 2.5, "general"),
    (re.compile(r'\b(never\s+done\s+this|just\s+starting|learning|tutorial)\b', re.I), 2.0, "general"),

    # Vague power specs
    (re.compile(r'\b(needs?\s+power|powered\s+by|runs?\s+on)\s+(batteries?|USB|wall)\b', re.I), 0.8, "power"),
    (re.compile(r'\b(5\s*volt|3\.3\s*volt|12\s*volt)\b', re.I), 0.3, "power"),  # Low weight — experts say this too

    # "a circuit/device/board that ..." phrasing
    (re.compile(r'\b(a\s+)?(device|circuit|module|system|board)\s+that\b', re.I), 1.2, "general"),
    (re.compile(r'\bjust\s+(need|want)\b', re.I), 0.8, "general"),

    # No-spec descriptions
    (re.compile(r'\b(small|tiny|compact|as\s+small\s+as\s+possible)\s+board\b', re.I), 0.5, "layout"),
    (re.compile(r'\b(cheap|inexpensive|low\s+cost|affordable)\b', re.I), 0.5, "general"),
]


# ── Analysis result types ─────────────────────────────────────────────────────

@dataclass
class SignalHit:
    pattern_name: str
    weight: float
    domain: str
    match_text: str


@dataclass
class MessageAnalysis:
    expert_score: float
    beginner_score: float
    expert_hits: list[SignalHit]
    beginner_hits: list[SignalHit]
    domains_expert: set[str]
    domains_beginner: set[str]

    @property
    def net_score(self) -> float:
        return self.expert_score - self.beginner_score


@dataclass
class SessionScore:
    """Accumulated score across all messages in a session."""
    expert_total: float = 0.0
    beginner_total: float = 0.0
    message_count: int = 0
    domains_expert: dict[str, float] = field(default_factory=dict)
    domains_beginner: dict[str, float] = field(default_factory=dict)


# ── Detector ──────────────────────────────────────────────────────────────────

class ExpertiseDetector:
    """
    Stateless analysis per message, stateful accumulation per session.
    Create one per session and call analyze() on each user message.
    """

    # How much net expert score is needed to call someone "expert"
    EXPERT_THRESHOLD = 2.0
    # How much net beginner score before calling "beginner"
    BEGINNER_THRESHOLD = 2.0
    # If expert > EXPERT_THRESHOLD but beginner > BEGINNER_CONTAMINATION in a
    # different domain, call it "mixed"
    BEGINNER_CONTAMINATION = 2.0

    def __init__(self):
        self._session = SessionScore()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, message: str) -> MessageAnalysis:
        """Analyze a single message and update session scores. Returns analysis."""
        analysis = self._analyze_message(message)
        self._accumulate(analysis)
        return analysis

    def level(self) -> ExpertiseLevel:
        """Return current expertise level from accumulated session data."""
        s = self._session
        if s.message_count == 0:
            return "unknown"

        net = s.expert_total - s.beginner_total

        # Need minimum evidence before committing
        total_signal = s.expert_total + s.beginner_total
        if total_signal < 1.5:
            return "unknown"

        # Expert: high net score
        if net >= self.EXPERT_THRESHOLD:
            # Check for beginner contamination in a domain where expert has no score
            beginner_only_domains = {
                d: score for d, score in s.domains_beginner.items()
                if score >= self.BEGINNER_CONTAMINATION
                and s.domains_expert.get(d, 0) < 1.0
            }
            if beginner_only_domains:
                return "mixed"
            return "expert"

        # Beginner: net score negative or low positive
        if net <= -self.BEGINNER_THRESHOLD or (s.beginner_total > self.BEGINNER_THRESHOLD and s.expert_total < 1.0):
            return "beginner"

        # Some of both → mixed
        if s.expert_total >= 2.0 and s.beginner_total >= 1.5:
            return "mixed"

        # Not enough signal
        return "unknown"

    def confidence(self) -> float:
        """Return confidence 0–1. Saturates quickly with strong signals."""
        total = self._session.expert_total + self._session.beginner_total
        # Saturate at ~10 total signal points
        return min(total / 10.0, 1.0)

    def domain_breakdown(self) -> dict[str, str]:
        """
        Per-domain expertise estimate.
        Returns {"power": "expert", "layout": "unknown", "rf": "beginner", ...}
        """
        all_domains = set(self._session.domains_expert) | set(self._session.domains_beginner)
        result = {}
        for domain in all_domains:
            e = self._session.domains_expert.get(domain, 0.0)
            b = self._session.domains_beginner.get(domain, 0.0)
            net = e - b
            if e + b < 0.5:
                result[domain] = "unknown"
            elif net >= 2.0:
                result[domain] = "expert"
            elif net <= -1.5:
                result[domain] = "beginner"
            else:
                result[domain] = "mixed"
        return result

    def reset(self):
        self._session = SessionScore()

    def summary(self) -> dict:
        return {
            "level": self.level(),
            "confidence": round(self.confidence(), 2),
            "expert_score": round(self._session.expert_total, 2),
            "beginner_score": round(self._session.beginner_total, 2),
            "message_count": self._session.message_count,
            "domain_breakdown": self.domain_breakdown(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _analyze_message(self, message: str) -> MessageAnalysis:
        expert_hits: list[SignalHit] = []
        beginner_hits: list[SignalHit] = []
        expert_domains: set[str] = set()
        beginner_domains: set[str] = set()
        expert_score = 0.0
        beginner_score = 0.0

        for pattern, weight, domain in _EXPERT_SIGNALS:
            matches = pattern.findall(message)
            if matches:
                # Unique match contribution (cap per pattern to avoid spam)
                hit_weight = weight * min(len(matches), 2)
                expert_score += hit_weight
                expert_domains.add(domain)
                match_text = matches[0] if isinstance(matches[0], str) else matches[0][0]
                expert_hits.append(SignalHit(
                    pattern_name=pattern.pattern[:40],
                    weight=hit_weight,
                    domain=domain,
                    match_text=str(match_text)[:30],
                ))

        for pattern, weight, domain in _BEGINNER_SIGNALS:
            matches = pattern.findall(message)
            if matches:
                hit_weight = weight * min(len(matches), 2)
                beginner_score += hit_weight
                beginner_domains.add(domain)
                match_text = matches[0] if isinstance(matches[0], str) else matches[0][0]
                beginner_hits.append(SignalHit(
                    pattern_name=pattern.pattern[:40],
                    weight=hit_weight,
                    domain=domain,
                    match_text=str(match_text)[:30],
                ))

        return MessageAnalysis(
            expert_score=expert_score,
            beginner_score=beginner_score,
            expert_hits=expert_hits,
            beginner_hits=beginner_hits,
            domains_expert=expert_domains,
            domains_beginner=beginner_domains,
        )

    def _accumulate(self, analysis: MessageAnalysis):
        s = self._session
        s.expert_total += analysis.expert_score
        s.beginner_total += analysis.beginner_score
        s.message_count += 1
        for domain in analysis.domains_expert:
            s.domains_expert[domain] = s.domains_expert.get(domain, 0.0) + analysis.expert_score
        for domain in analysis.domains_beginner:
            s.domains_beginner[domain] = s.domains_beginner.get(domain, 0.0) + analysis.beginner_score


# ── Convenience function (stateless, single-message) ─────────────────────────

def quick_classify(text: str) -> ExpertiseLevel:
    """
    Quick one-shot classification of a single message.
    Use ExpertiseDetector for multi-turn accuracy.
    """
    d = ExpertiseDetector()
    d.analyze(text)
    return d.level()
