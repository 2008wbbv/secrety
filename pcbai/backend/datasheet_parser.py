"""
datasheet_parser.py
-------------------
Two-phase PDF datasheet extraction:

  Phase 1 — PDF extraction:
    pdfplumber extracts full text + tables from the PDF.
    PyMuPDF (fitz) used as fallback / for image-heavy PDFs.
    Output: raw text string + list of table dicts.

  Phase 2 — Claude parsing:
    Extracted text sent to Claude with a structured extraction prompt.
    Claude returns a JSON block with all constraint fields.
    Fallback: heuristic regex patterns for critical values if Claude unavailable.

The resulting DatasheetConstraints object feeds into:
  - system_prompt.py (board context)
  - simulation/ calculators (power budget, trace width)
  - KiCad control loop (decoupling placement, keepout zones)
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger("pcbai.datasheet_parser")

# Maximum characters of PDF text to send to Claude.
# Most datasheets are <500K chars; we take the first 80K which covers
# the datasheet header, features, pin descriptions, and application circuits.
MAX_TEXT_CHARS = 80_000

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Pin:
    number: str
    name: str
    function: str
    notes: str = ""


@dataclass
class DecouplingRequirement:
    """A single recommended decoupling capacitor."""
    pin_or_net: str          # e.g. "VCC", "pin 3", "AVDD"
    value_uf: float          # capacitance in µF
    type: str                # "ceramic", "electrolytic", "MLCC", etc.
    max_distance_mm: float   # max placement distance from pin (0 = no spec)
    notes: str = ""


@dataclass
class AbsMaxRatings:
    vcc_max_v: float | None = None
    vcc_min_v: float | None = None
    icc_max_ma: float | None = None
    power_max_mw: float | None = None
    temp_max_c: float | None = None
    temp_min_c: float | None = None


@dataclass
class OperatingConditions:
    vcc_nom_v: float | None = None
    vcc_range_v: tuple[float, float] | None = None
    icc_typical_ma: float | None = None
    icc_max_ma: float | None = None
    freq_max_mhz: float | None = None


@dataclass
class LayoutNote:
    category: str           # "thermal", "keepout", "ground_plane", "routing", "via", "general"
    description: str
    critical: bool = False  # True = must be followed or device won't work


@dataclass
class ImpedanceRequirement:
    net_or_pair: str
    target_ohms: float
    tolerance_pct: float = 10.0
    layer_notes: str = ""


@dataclass
class DifferentialPair:
    positive_pin: str
    negative_pin: str
    net_base_name: str
    max_skew_mm: float = 0.0
    impedance_ohms: float = 0.0


@dataclass
class DatasheetConstraints:
    """All design-relevant information extracted from one datasheet."""
    filename: str
    component_name: str = ""
    manufacturer: str = ""
    package: str = ""                          # e.g. "QFN-48", "SOIC-8"
    pins: list[Pin] = field(default_factory=list)
    decoupling: list[DecouplingRequirement] = field(default_factory=list)
    layout_notes: list[LayoutNote] = field(default_factory=list)
    abs_max: AbsMaxRatings = field(default_factory=AbsMaxRatings)
    operating: OperatingConditions = field(default_factory=OperatingConditions)
    impedance_requirements: list[ImpedanceRequirement] = field(default_factory=list)
    differential_pairs: list[DifferentialPair] = field(default_factory=list)
    footprint_notes: str = ""
    confidence: float = 0.0   # 0–1: how confident we are in the extraction
    raw_text_chars: int = 0   # Characters extracted from PDF
    parse_method: str = ""    # "claude" | "heuristic" | "failed"

    def to_dict(self) -> dict:
        return asdict(self)

    def beginner_summary(self) -> str:
        """Plain-English summary for beginner users."""
        lines = [f"**{self.component_name}** ({self.package})"]

        if self.decoupling:
            lines.append("\n**Decoupling capacitors required:**")
            for d in self.decoupling:
                dist = f", within {d.max_distance_mm:.0f}mm of pin" if d.max_distance_mm > 0 else ""
                lines.append(f"  • {d.value_uf:.3g}µF {d.type} on {d.pin_or_net}{dist}")

        critical = [n for n in self.layout_notes if n.critical]
        if critical:
            lines.append("\n**Critical layout rules:**")
            for note in critical:
                lines.append(f"  ⚠️ {note.description}")

        if self.abs_max.vcc_max_v:
            lines.append(f"\n**Max supply voltage:** {self.abs_max.vcc_max_v}V — never exceed this")
        if self.operating.vcc_nom_v:
            lines.append(f"**Nominal supply:** {self.operating.vcc_nom_v}V")
        if self.operating.icc_typical_ma:
            lines.append(f"**Typical current draw:** {self.operating.icc_typical_ma:.1f}mA")

        return "\n".join(lines)

    def expert_summary(self) -> str:
        """Compact technical summary for expert users."""
        parts = [f"{self.component_name} | {self.package}"]
        if self.operating.vcc_range_v:
            lo, hi = self.operating.vcc_range_v
            parts.append(f"VCC: {lo}–{hi}V")
        if self.operating.icc_max_ma:
            parts.append(f"Icc max: {self.operating.icc_max_ma:.1f}mA")
        if self.abs_max.vcc_max_v:
            parts.append(f"Vmax: {self.abs_max.vcc_max_v}V")
        if self.decoupling:
            dec_str = ", ".join(f"{d.value_uf:.3g}µF@{d.pin_or_net}" for d in self.decoupling)
            parts.append(f"Decoupling: {dec_str}")
        if self.differential_pairs:
            dp_str = ", ".join(f"{dp.net_base_name}({dp.impedance_ohms:.0f}Ω)" for dp in self.differential_pairs)
            parts.append(f"Diff pairs: {dp_str}")
        critical = [n.description[:60] for n in self.layout_notes if n.critical]
        if critical:
            parts.append("Critical: " + " | ".join(critical))
        return " | ".join(parts)


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_text_pdfplumber(data: bytes) -> tuple[str, list[dict]]:
    """Extract text and tables from PDF bytes using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed — trying PyMuPDF")
        return _extract_text_pymupdf(data)

    text_parts = []
    tables = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(f"[Page {page_num}]\n{page_text}")
                for table in (page.extract_tables() or []):
                    if table:
                        tables.append({
                            "page": page_num,
                            "rows": [[str(c) if c is not None else "" for c in row] for row in table],
                        })
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s — trying PyMuPDF", exc)
        return _extract_text_pymupdf(data)

    return "\n\n".join(text_parts), tables


def _extract_text_pymupdf(data: bytes) -> tuple[str, list[dict]]:
    """Fallback: extract text using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("Neither pdfplumber nor PyMuPDF available")
        return "", []

    text_parts = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"[Page {page_num}]\n{page_text}")
        doc.close()
    except Exception as exc:
        logger.error("PyMuPDF extraction failed: %s", exc)
        return "", []

    return "\n\n".join(text_parts), []


# ── Claude-based structured extraction ───────────────────────────────────────

_EXTRACTION_PROMPT = """\
You are analyzing a semiconductor datasheet. Extract all design-relevant information
and return it as a single JSON object. Return ONLY the JSON — no explanation, no markdown.

Required JSON schema:
{
  "component_name": "string — full component name/part number",
  "manufacturer": "string",
  "package": "string — e.g. QFN-48, SOIC-8, TO-220",
  "pins": [
    {"number": "1", "name": "VCC", "function": "Power supply input", "notes": ""}
  ],
  "decoupling": [
    {
      "pin_or_net": "VCC",
      "value_uf": 0.1,
      "type": "ceramic MLCC",
      "max_distance_mm": 1.0,
      "notes": "100nF X5R or better"
    }
  ],
  "layout_notes": [
    {
      "category": "thermal|keepout|ground_plane|routing|via|general",
      "description": "string",
      "critical": true
    }
  ],
  "abs_max": {
    "vcc_max_v": 5.5,
    "vcc_min_v": -0.3,
    "icc_max_ma": 500,
    "power_max_mw": 1000,
    "temp_max_c": 125,
    "temp_min_c": -40
  },
  "operating": {
    "vcc_nom_v": 3.3,
    "vcc_range_v": [3.0, 3.6],
    "icc_typical_ma": 50,
    "icc_max_ma": 100,
    "freq_max_mhz": 100
  },
  "impedance_requirements": [
    {
      "net_or_pair": "USB_DP/USB_DM",
      "target_ohms": 90,
      "tolerance_pct": 10,
      "layer_notes": "microstrip on outer layer"
    }
  ],
  "differential_pairs": [
    {
      "positive_pin": "DP",
      "negative_pin": "DM",
      "net_base_name": "USB",
      "max_skew_mm": 0.5,
      "impedance_ohms": 90
    }
  ],
  "footprint_notes": "string — thermal pad, exposed pad, land pattern notes"
}

Rules:
- Use null for any field you cannot find in the datasheet
- For decoupling, include ALL recommended bypass caps from the application circuit
- Mark layout_notes as critical=true if the datasheet says the device will not function
  correctly without the guideline (e.g. exposed thermal pad must connect to ground)
- Include ALL differential pairs (USB, LVDS, Ethernet, etc.)
- All pin entries must have at least number and name
- If multiple packages exist, extract data for the most common/featured one

Datasheet text:
"""


async def _parse_with_claude(text: str, tables: list[dict], client: Any) -> DatasheetConstraints | None:
    """Send extracted text to Claude for structured parsing."""
    if client is None:
        return None

    # Build the message: include table summaries as extra context
    table_summary = ""
    if tables:
        table_summary = "\n\nExtracted tables:\n"
        for t in tables[:10]:  # Limit to first 10 tables
            rows = t.get("rows", [])[:20]  # First 20 rows per table
            table_summary += f"\n[Page {t['page']}]\n"
            for row in rows:
                table_summary += " | ".join(row) + "\n"

    # Truncate text to fit context
    combined = text[:MAX_TEXT_CHARS] + table_summary
    prompt = _EXTRACTION_PROMPT + combined

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        if not response.content:
            raise ValueError("Claude returned empty content")
        raw = response.content[0].text.strip()

        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        data = json.loads(raw)
        return _dict_to_constraints("", data)

    except json.JSONDecodeError as exc:
        logger.warning("Claude returned non-JSON for datasheet: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Claude datasheet parsing failed: %s", exc)
        return None


def _dict_to_constraints(filename: str, data: dict) -> DatasheetConstraints:
    """Convert Claude's JSON response to a DatasheetConstraints object."""
    abs_max_data = data.get("abs_max") or {}
    op_data = data.get("operating") or {}

    vcc_range = None
    if op_data.get("vcc_range_v"):
        r = op_data["vcc_range_v"]
        try:
            vcc_range = (float(r[0]), float(r[1]))
        except (TypeError, IndexError, ValueError):
            pass

    return DatasheetConstraints(
        filename=filename,
        component_name=data.get("component_name") or "",
        manufacturer=data.get("manufacturer") or "",
        package=data.get("package") or "",
        pins=[
            Pin(
                number=str(p.get("number", "")),
                name=str(p.get("name", "")),
                function=str(p.get("function", "")),
                notes=str(p.get("notes", "")),
            )
            for p in (data.get("pins") or [])
        ],
        decoupling=[
            DecouplingRequirement(
                pin_or_net=str(d.get("pin_or_net", "")),
                value_uf=float(d.get("value_uf") or 0),
                type=str(d.get("type", "ceramic")),
                max_distance_mm=float(d.get("max_distance_mm") or 0),
                notes=str(d.get("notes", "")),
            )
            for d in (data.get("decoupling") or [])
        ],
        layout_notes=[
            LayoutNote(
                category=str(n.get("category", "general")),
                description=str(n.get("description", "")),
                critical=bool(n.get("critical", False)),
            )
            for n in (data.get("layout_notes") or [])
        ],
        abs_max=AbsMaxRatings(
            vcc_max_v=_float_or_none(abs_max_data.get("vcc_max_v")),
            vcc_min_v=_float_or_none(abs_max_data.get("vcc_min_v")),
            icc_max_ma=_float_or_none(abs_max_data.get("icc_max_ma")),
            power_max_mw=_float_or_none(abs_max_data.get("power_max_mw")),
            temp_max_c=_float_or_none(abs_max_data.get("temp_max_c")),
            temp_min_c=_float_or_none(abs_max_data.get("temp_min_c")),
        ),
        operating=OperatingConditions(
            vcc_nom_v=_float_or_none(op_data.get("vcc_nom_v")),
            vcc_range_v=vcc_range,
            icc_typical_ma=_float_or_none(op_data.get("icc_typical_ma")),
            icc_max_ma=_float_or_none(op_data.get("icc_max_ma")),
            freq_max_mhz=_float_or_none(op_data.get("freq_max_mhz")),
        ),
        impedance_requirements=[
            ImpedanceRequirement(
                net_or_pair=str(r.get("net_or_pair", "")),
                target_ohms=float(r.get("target_ohms") or 0),
                tolerance_pct=float(r.get("tolerance_pct") or 10),
                layer_notes=str(r.get("layer_notes", "")),
            )
            for r in (data.get("impedance_requirements") or [])
        ],
        differential_pairs=[
            DifferentialPair(
                positive_pin=str(p.get("positive_pin", "")),
                negative_pin=str(p.get("negative_pin", "")),
                net_base_name=str(p.get("net_base_name", "")),
                max_skew_mm=float(p.get("max_skew_mm") or 0),
                impedance_ohms=float(p.get("impedance_ohms") or 0),
            )
            for p in (data.get("differential_pairs") or [])
        ],
        footprint_notes=str(data.get("footprint_notes") or ""),
        confidence=0.85,
        parse_method="claude",
    )


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Heuristic fallback ────────────────────────────────────────────────────────

def _heuristic_parse(filename: str, text: str) -> DatasheetConstraints:
    """
    Best-effort heuristic extraction when Claude is unavailable.
    Covers the most critical values: voltages, currents, and obvious layout rules.
    """
    c = DatasheetConstraints(filename=filename, parse_method="heuristic", confidence=0.3)

    # Component name: first line or title-ish line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        c.component_name = lines[0][:80]

    # Absolute max VCC
    m = re.search(r'(?:supply\s*voltage|VCC|VDD)[^\n]*?(\d+\.?\d*)\s*V\s*(?:max|maximum|abs)', text, re.I)
    if m:
        c.abs_max.vcc_max_v = float(m.group(1))

    # Typical supply current
    m = re.search(r'(?:supply\s*current|ICC|IDD)[^\n]*?(\d+\.?\d*)\s*(?:mA|µA|uA)', text, re.I)
    if m:
        val = float(m.group(1))
        if 'µA' in m.group(0) or 'uA' in m.group(0):
            val /= 1000
        c.operating.icc_typical_ma = val

    # Thermal pad note
    if re.search(r'thermal\s*pad|exposed\s*pad|epad', text, re.I):
        c.layout_notes.append(LayoutNote(
            category="thermal",
            description="Thermal/exposed pad detected — must be soldered to PCB thermal relief. Add vias to ground plane.",
            critical=True,
        ))

    # Decoupling caps mentioned near VCC/VDD
    for m in re.finditer(r'(\d+\.?\d*)\s*(nF|µF|uF|pF)\s*(?:ceramic|MLCC|bypass|decoupling)', text, re.I):
        val_str = m.group(1)
        unit = m.group(2).lower().replace('µ', 'u')
        val = float(val_str)
        if unit == 'nf':
            val /= 1000
        elif unit == 'pf':
            val /= 1_000_000
        c.decoupling.append(DecouplingRequirement(
            pin_or_net="VCC",
            value_uf=round(val, 6),
            type="ceramic",
            max_distance_mm=2.0,
        ))
        if len(c.decoupling) >= 5:
            break

    return c


# ── Main class ────────────────────────────────────────────────────────────────

class DatasheetParser:
    """
    Parses manufacturer PDF datasheets into structured DatasheetConstraints.

    Attach an Anthropic client for full Claude-powered extraction.
    Without it, heuristic fallback is used.
    """

    def __init__(self, anthropic_client: Any = None):
        self._client = anthropic_client
        # Cache: filename hash → DatasheetConstraints
        self._cache: dict[str, DatasheetConstraints] = {}

    def set_client(self, client: Any):
        self._client = client

    async def parse(self, filename: str, content: bytes) -> dict:
        """
        Parse a PDF datasheet. Returns a dict suitable for the API response.
        """
        if not content:
            return {"parsed": False, "error": "Empty file", "filename": filename}

        cache_key = hashlib.sha256(content).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.info("Datasheet cache hit: %s", filename)
            return self._to_response(cached, cached=True)

        logger.info("Parsing datasheet: %s (%d bytes)", filename, len(content))

        # Phase 1: PDF text extraction
        text, tables = _extract_text_pdfplumber(content)
        char_count = len(text)

        if char_count < 100:
            logger.warning("Extracted very little text from %s (%d chars) — may be image-only PDF", filename, char_count)

        # Phase 2: Structured parsing
        constraints: DatasheetConstraints | None = None

        if self._client and char_count > 50:
            constraints = await _parse_with_claude(text, tables, self._client)

        if constraints is None:
            logger.info("Using heuristic fallback for %s", filename)
            constraints = _heuristic_parse(filename, text)

        constraints.filename = filename
        constraints.raw_text_chars = char_count
        self._cache[cache_key] = constraints

        return self._to_response(constraints, cached=False)

    @staticmethod
    def _to_response(c: DatasheetConstraints, cached: bool = False) -> dict:
        return {
            "parsed": True,
            "cached": cached,
            "filename": c.filename,
            "component_name": c.component_name,
            "manufacturer": c.manufacturer,
            "package": c.package,
            "pin_count": len(c.pins),
            "decoupling_count": len(c.decoupling),
            "critical_layout_notes": [n.description for n in c.layout_notes if n.critical],
            "has_differential_pairs": len(c.differential_pairs) > 0,
            "confidence": c.confidence,
            "parse_method": c.parse_method,
            "raw_text_chars": c.raw_text_chars,
            "constraints": c.to_dict(),
            "beginner_summary": c.beginner_summary(),
            "expert_summary": c.expert_summary(),
        }
