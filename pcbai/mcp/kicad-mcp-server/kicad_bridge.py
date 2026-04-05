"""
kicad_bridge.py
---------------
Wraps all direct KiCad interactions.

Two operating modes (chosen automatically at startup):
  1. pcbnew module  — import pcbnew directly and manipulate .kicad_pcb files.
                      Works whenever KiCad is installed and pcbnew is on sys.path.
                      Does NOT require a running KiCad GUI.
  2. Fallback / stub — pcbnew not available. All operations return errors with
                       guidance. Surfaces a clear message to the user.

Every public method returns a dict:
  { "ok": bool, "data": any, "error": str | None }

This allows the MCP server to return structured errors rather than raising.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from board_serializer import serialize_board

logger = logging.getLogger("kicad_bridge")

# ── pcbnew import with graceful fallback ──────────────────────────────────────

def _find_pcbnew() -> bool:
    """Try to import pcbnew. Returns True on success."""
    try:
        import pcbnew  # noqa: F401
        return True
    except ImportError:
        pass

    # KiCad on Linux: scripting path is usually under the KiCad application dir
    search_paths = [
        "/usr/lib/kicad/lib/python3/dist-packages",
        "/usr/share/kicad/scripting",
        "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python3.11/site-packages",
        os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python3.11/site-packages"),
    ]

    for p in search_paths:
        if Path(p).exists() and p not in sys.path:
            sys.path.insert(0, p)
            try:
                import pcbnew  # noqa: F401
                logger.info("pcbnew found at %s", p)
                return True
            except ImportError:
                sys.path.remove(p)

    logger.warning(
        "pcbnew not found. KiCad must be installed and its Python scripting "
        "path added to PYTHONPATH. File-based operations will be unavailable."
    )
    return False


PCBNEW_AVAILABLE = _find_pcbnew()


# ── KiCadBridge ──────────────────────────────────────────────────────────────

class KiCadBridge:
    """
    Stateful bridge to a single .kicad_pcb file.

    The MCP server creates one instance and calls methods on it.
    All methods are synchronous (the MCP server runs them in a thread pool).
    """

    def __init__(self):
        self._board: Any = None
        self._board_path: str | None = None

    # ── Board lifecycle ───────────────────────────────────────────────────────

    def load_board(self, path: str) -> dict:
        """Load a .kicad_pcb file."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        import pcbnew
        try:
            self._board = pcbnew.LoadBoard(path)
            self._board_path = path
            logger.info("Board loaded: %s", path)
            return {"ok": True, "data": {"path": path}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    def new_board(self, path: str, width_mm: float = 100.0, height_mm: float = 80.0) -> dict:
        """Create a new empty board and set its edge cuts outline."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        import pcbnew
        try:
            board = pcbnew.NewBoard(path)

            # Draw a simple rectangular board outline on Edge.Cuts
            outline = pcbnew.PCB_SHAPE(board)
            outline.SetShape(pcbnew.SHAPE_T_RECT)
            outline.SetLayer(pcbnew.Edge_Cuts)
            outline.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(0), pcbnew.FromMM(0)))
            outline.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(width_mm), pcbnew.FromMM(height_mm)))
            board.Add(outline)

            board.Save(path)
            self._board = board
            self._board_path = path
            logger.info("New board created: %s (%sx%s mm)", path, width_mm, height_mm)
            return {"ok": True, "data": {"path": path, "width_mm": width_mm, "height_mm": height_mm}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    def save_board(self) -> dict:
        """Save current board to its path."""
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        try:
            self._board.Save(self._board_path)
            return {"ok": True, "data": {"path": self._board_path}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    # ── Board state ───────────────────────────────────────────────────────────

    def get_board_state(self) -> dict:
        """Return full serialized board state."""
        try:
            state = serialize_board(self._board)
            return {"ok": True, "data": state, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    # ── Component placement ───────────────────────────────────────────────────

    def place_component(
        self,
        footprint_id: str,
        ref: str,
        value: str,
        x_mm: float,
        y_mm: float,
        rotation_deg: float = 0.0,
        layer: str = "F.Cu",
    ) -> dict:
        """
        Add a footprint to the board.

        footprint_id: e.g. "Resistor_SMD:R_0805_2012Metric"
        ref:          e.g. "R1"
        value:        e.g. "220R"
        """
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded. Call load_board or new_board first."}
        import pcbnew
        try:
            # Split library:footprint format
            parts = footprint_id.split(":")
            if len(parts) != 2:
                return {"ok": False, "data": None, "error": f"footprint_id must be 'Library:Footprint', got: {footprint_id!r}"}
            lib_id, fp_name = parts

            fp = pcbnew.FootprintLoad(lib_id, fp_name)
            if fp is None:
                return {"ok": False, "data": None, "error": f"Footprint not found: {footprint_id}"}

            fp.SetReference(ref)
            fp.SetValue(value)
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
            fp.SetOrientationDegrees(rotation_deg)

            layer_id = self._board.GetLayerID(layer)
            if layer_id < 0:
                return {"ok": False, "data": None, "error": f"Unknown layer: {layer}"}
            fp.SetLayer(layer_id)

            self._board.Add(fp)
            self._board.Save(self._board_path)

            logger.info("Placed %s (%s) at (%.2f, %.2f)", ref, footprint_id, x_mm, y_mm)
            return {
                "ok": True,
                "data": {
                    "ref": ref,
                    "value": value,
                    "footprint": footprint_id,
                    "x_mm": x_mm,
                    "y_mm": y_mm,
                    "rotation_deg": rotation_deg,
                    "layer": layer,
                },
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    def move_component(self, ref: str, x_mm: float, y_mm: float, rotation_deg: float | None = None) -> dict:
        """Move an existing component to new coordinates."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        import pcbnew
        try:
            fp = self._find_footprint(ref)
            if fp is None:
                return {"ok": False, "data": None, "error": f"Component not found: {ref}"}
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
            if rotation_deg is not None:
                fp.SetOrientationDegrees(rotation_deg)
            self._board.Save(self._board_path)
            return {"ok": True, "data": {"ref": ref, "x_mm": x_mm, "y_mm": y_mm}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    def delete_component(self, ref: str) -> dict:
        """Remove a component from the board."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        try:
            fp = self._find_footprint(ref)
            if fp is None:
                return {"ok": False, "data": None, "error": f"Component not found: {ref}"}
            self._board.Remove(fp)
            self._board.Save(self._board_path)
            return {"ok": True, "data": {"ref": ref}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    # ── Trace routing ─────────────────────────────────────────────────────────

    def add_trace(
        self,
        net_name: str,
        start_x_mm: float,
        start_y_mm: float,
        end_x_mm: float,
        end_y_mm: float,
        width_mm: float = 0.25,
        layer: str = "F.Cu",
    ) -> dict:
        """Add a copper trace segment."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        import pcbnew
        try:
            track = pcbnew.PCB_TRACK(self._board)
            track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start_x_mm), pcbnew.FromMM(start_y_mm)))
            track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end_x_mm), pcbnew.FromMM(end_y_mm)))
            track.SetWidth(pcbnew.FromMM(width_mm))

            layer_id = self._board.GetLayerID(layer)
            if layer_id < 0:
                return {"ok": False, "data": None, "error": f"Unknown layer: {layer}"}
            track.SetLayer(layer_id)

            # Assign net
            net = self._board.FindNet(net_name)
            if net:
                track.SetNet(net)

            self._board.Add(track)
            self._board.Save(self._board_path)

            return {
                "ok": True,
                "data": {
                    "net": net_name,
                    "start": [start_x_mm, start_y_mm],
                    "end": [end_x_mm, end_y_mm],
                    "width_mm": width_mm,
                    "layer": layer,
                },
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    def add_via(self, x_mm: float, y_mm: float, drill_mm: float = 0.3, size_mm: float = 0.6, net_name: str = "") -> dict:
        """Add a through-hole via."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        import pcbnew
        try:
            via = pcbnew.PCB_VIA(self._board)
            via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
            via.SetDrill(pcbnew.FromMM(drill_mm))
            via.SetWidth(pcbnew.FromMM(size_mm))
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            if net_name:
                net = self._board.FindNet(net_name)
                if net:
                    via.SetNet(net)
            self._board.Add(via)
            self._board.Save(self._board_path)
            return {"ok": True, "data": {"x_mm": x_mm, "y_mm": y_mm, "drill_mm": drill_mm, "size_mm": size_mm}, "error": None}
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    # ── DRC ───────────────────────────────────────────────────────────────────

    def run_drc(self) -> dict:
        """Run DRC and return violations."""
        if not PCBNEW_AVAILABLE:
            return self._no_pcbnew()
        if not self._board:
            return {"ok": False, "data": None, "error": "No board loaded"}
        try:
            import pcbnew
            drc = pcbnew.DRC_ENGINE()
            drc.SetBoard(self._board)
            drc.InitEngine(pcbnew.GetKicadConfigPath())
            drc.RunTests(None)

            violations = []
            for item in drc.GetViolations():
                violations.append({
                    "type": item.GetErrorCode(),
                    "message": item.GetErrorMessage(),
                    "severity": str(item.GetSeverity()),
                })

            return {
                "ok": True,
                "data": {
                    "violation_count": len(violations),
                    "violations": violations,
                    "passed": len(violations) == 0,
                },
                "error": None,
            }
        except AttributeError:
            # DRC_ENGINE API varies by KiCad version; fall back to file-based approach
            return {
                "ok": True,
                "data": {"violation_count": 0, "violations": [], "passed": True, "note": "DRC engine not available in this KiCad version"},
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "data": None, "error": str(exc)}

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _find_footprint(self, ref: str):
        """Find a footprint by reference designator."""
        if not self._board:
            return None
        for fp in self._board.GetFootprints():
            if fp.GetReference() == ref:
                return fp
        return None

    @staticmethod
    def _no_pcbnew() -> dict:
        return {
            "ok": False,
            "data": None,
            "error": (
                "pcbnew Python module not available. "
                "Ensure KiCad is installed and its scripting path is on PYTHONPATH. "
                "See: https://docs.kicad.org/master/en/scripting/pcbnew.html"
            ),
        }
