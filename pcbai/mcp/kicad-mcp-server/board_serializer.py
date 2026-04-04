"""
board_serializer.py
-------------------
Converts a KiCad board (pcbnew.BOARD) into a plain Python dict that Claude can
reason about without any KiCad API knowledge.

Called by kicad_bridge.py after every mutating operation so the backend always
has an up-to-date snapshot.
"""

from __future__ import annotations
from typing import Any


def serialize_board(board: Any) -> dict:
    """
    Convert a pcbnew.BOARD object to a JSON-serializable dict.

    Returns a minimal but complete picture:
      - Board dimensions and origin
      - Layer names in use
      - All footprints (components) with pads and net assignments
      - All copper traces and vias
      - All nets
      - Zones (copper pours)

    If pcbnew is not available (board is None), returns an empty skeleton.
    """
    if board is None:
        return _empty_state()

    try:
        return {
            "filename": str(board.GetFileName()),
            "width_mm": _to_mm(board.GetBoardEdgesBoundingBox().GetWidth()),
            "height_mm": _to_mm(board.GetBoardEdgesBoundingBox().GetHeight()),
            "layers": _serialize_layers(board),
            "components": _serialize_footprints(board),
            "traces": _serialize_tracks(board),
            "vias": _serialize_vias(board),
            "zones": _serialize_zones(board),
            "nets": _serialize_nets(board),
            "drc_violations": [],  # Populated separately after DRC run
        }
    except Exception as exc:
        return {**_empty_state(), "error": str(exc)}


# ── Private helpers ───────────────────────────────────────────────────────────

def _empty_state() -> dict:
    return {
        "filename": None,
        "width_mm": 0.0,
        "height_mm": 0.0,
        "layers": [],
        "components": [],
        "traces": [],
        "vias": [],
        "zones": [],
        "nets": [],
        "drc_violations": [],
    }


def _to_mm(iu: int) -> float:
    """Convert KiCad internal units (nanometres) to millimetres, rounded."""
    try:
        import pcbnew
        return round(pcbnew.ToMM(iu), 4)
    except Exception:
        return round(iu / 1_000_000, 4)


def _serialize_layers(board: Any) -> list[str]:
    try:
        enabled = board.GetEnabledLayers()
        names = []
        for layer_id in range(64):
            if enabled.Contains(layer_id):
                name = board.GetLayerName(layer_id)
                if name:
                    names.append(name)
        return names
    except Exception:
        return []


def _serialize_footprints(board: Any) -> list[dict]:
    result = []
    try:
        for fp in board.GetFootprints():
            pads = []
            for pad in fp.Pads():
                net = pad.GetNetname() or ""
                pads.append({
                    "number": pad.GetNumber(),
                    "x_mm": _to_mm(pad.GetX()),
                    "y_mm": _to_mm(pad.GetY()),
                    "net": net,
                    "shape": str(pad.GetShape()),
                })
            result.append({
                "ref": fp.GetReference(),
                "value": fp.GetValue(),
                "footprint": fp.GetFPIDAsString(),
                "x_mm": _to_mm(fp.GetX()),
                "y_mm": _to_mm(fp.GetY()),
                "rotation_deg": fp.GetOrientationDegrees(),
                "layer": board.GetLayerName(fp.GetLayer()),
                "pads": pads,
                "locked": fp.IsLocked(),
            })
    except Exception:
        pass
    return result


def _serialize_tracks(board: Any) -> list[dict]:
    result = []
    try:
        import pcbnew
        for track in board.GetTracks():
            if track.GetClass() == "PCB_TRACK":
                result.append({
                    "net": track.GetNetname(),
                    "layer": board.GetLayerName(track.GetLayer()),
                    "start_x_mm": _to_mm(track.GetStart().x),
                    "start_y_mm": _to_mm(track.GetStart().y),
                    "end_x_mm": _to_mm(track.GetEnd().x),
                    "end_y_mm": _to_mm(track.GetEnd().y),
                    "width_mm": _to_mm(track.GetWidth()),
                })
    except Exception:
        pass
    return result


def _serialize_vias(board: Any) -> list[dict]:
    result = []
    try:
        for track in board.GetTracks():
            if track.GetClass() == "PCB_VIA":
                result.append({
                    "net": track.GetNetname(),
                    "x_mm": _to_mm(track.GetX()),
                    "y_mm": _to_mm(track.GetY()),
                    "drill_mm": _to_mm(track.GetDrillValue()),
                    "size_mm": _to_mm(track.GetWidth()),
                })
    except Exception:
        pass
    return result


def _serialize_zones(board: Any) -> list[dict]:
    result = []
    try:
        for zone in board.Zones():
            result.append({
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(zone.GetLayer()),
                "filled": zone.IsFilled(),
            })
    except Exception:
        pass
    return result


def _serialize_nets(board: Any) -> list[str]:
    try:
        return sorted(
            name
            for name in (
                board.FindNet(i).GetNetname()
                for i in range(board.GetNetCount())
            )
            if name
        )
    except Exception:
        return []
