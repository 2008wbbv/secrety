"""
PCB.AI KiCad MCP Server
-----------------------
A hardened MCP server that exposes KiCad board manipulation as tools.

Transport: stdio (JSON-RPC over stdin/stdout).
Launched as a subprocess by the Python FastAPI backend.

Hardening vs. bare community servers:
  - All tool calls wrapped in try/except — the server never crashes on a bad call
  - Every response has { ok, data, error } — consumers can always check ok
  - Graceful degradation when pcbnew is unavailable
  - Logs to stderr (stdout is reserved for MCP protocol)
"""

import asyncio
import logging
import sys

# Redirect logging to stderr so it doesn't corrupt the MCP stdio stream
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kicad_mcp_server")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from kicad_bridge import KiCadBridge, PCBNEW_AVAILABLE

# ── Server and bridge singletons ─────────────────────────────────────────────

server = Server("kicad-mcp-server")
bridge = KiCadBridge()


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_board_state",
            description=(
                "Return the full current board state as JSON: components, traces, "
                "vias, zones, nets, and board dimensions. Call this after any "
                "mutating operation to confirm the result."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="new_board",
            description="Create a new empty KiCad board file with a rectangular outline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path for the new .kicad_pcb file"},
                    "width_mm": {"type": "number", "description": "Board width in mm", "default": 100.0},
                    "height_mm": {"type": "number", "description": "Board height in mm", "default": 80.0},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="load_board",
            description="Load an existing .kicad_pcb file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the .kicad_pcb file"},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="save_board",
            description="Save the current board to disk.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="place_component",
            description=(
                "Place a KiCad footprint on the board. "
                "footprint_id must be 'Library:FootprintName' format, e.g. "
                "'Resistor_SMD:R_0805_2012Metric'. "
                "The component is saved to the board file immediately."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "footprint_id": {"type": "string", "description": "KiCad footprint ID, e.g. 'Resistor_SMD:R_0805_2012Metric'"},
                    "ref": {"type": "string", "description": "Reference designator, e.g. 'R1'"},
                    "value": {"type": "string", "description": "Component value, e.g. '220R'"},
                    "x_mm": {"type": "number", "description": "X coordinate in mm"},
                    "y_mm": {"type": "number", "description": "Y coordinate in mm"},
                    "rotation_deg": {"type": "number", "description": "Rotation in degrees (default 0)", "default": 0.0},
                    "layer": {"type": "string", "description": "Layer name (default 'F.Cu')", "default": "F.Cu"},
                },
                "required": ["footprint_id", "ref", "value", "x_mm", "y_mm"],
            },
        ),
        types.Tool(
            name="move_component",
            description="Move an existing component to new coordinates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "x_mm": {"type": "number"},
                    "y_mm": {"type": "number"},
                    "rotation_deg": {"type": "number", "description": "Optional new rotation"},
                },
                "required": ["ref", "x_mm", "y_mm"],
            },
        ),
        types.Tool(
            name="delete_component",
            description="Remove a component from the board by reference designator.",
            inputSchema={
                "type": "object",
                "properties": {"ref": {"type": "string"}},
                "required": ["ref"],
            },
        ),
        types.Tool(
            name="add_trace",
            description=(
                "Add a copper trace segment between two points. "
                "Set width_mm according to IPC-2221 calculations for the net current."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "net_name": {"type": "string"},
                    "start_x_mm": {"type": "number"},
                    "start_y_mm": {"type": "number"},
                    "end_x_mm": {"type": "number"},
                    "end_y_mm": {"type": "number"},
                    "width_mm": {"type": "number", "default": 0.25},
                    "layer": {"type": "string", "default": "F.Cu"},
                },
                "required": ["net_name", "start_x_mm", "start_y_mm", "end_x_mm", "end_y_mm"],
            },
        ),
        types.Tool(
            name="add_via",
            description="Add a through-hole via.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x_mm": {"type": "number"},
                    "y_mm": {"type": "number"},
                    "drill_mm": {"type": "number", "default": 0.3},
                    "size_mm": {"type": "number", "default": 0.6},
                    "net_name": {"type": "string", "default": ""},
                },
                "required": ["x_mm", "y_mm"],
            },
        ),
        types.Tool(
            name="run_drc",
            description=(
                "Run KiCad DRC and return all violations. "
                "Call this after placement and routing. "
                "The agentic loop should call this and fix violations before proceeding."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="server_info",
            description="Return server status and pcbnew availability.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ── Tool call dispatch ────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Dispatch tool calls to the KiCadBridge. Never raises — always returns JSON."""
    import json

    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:
        result = {"ok": False, "data": None, "error": f"Unexpected server error: {exc}"}

    return [types.TextContent(type="text", text=json.dumps(result, default=str))]


async def _dispatch(name: str, args: dict) -> dict:
    loop = asyncio.get_event_loop()

    # Run synchronous bridge methods in a thread pool to avoid blocking the event loop
    def _run_sync(fn, *a, **kw):
        return fn(*a, **kw)

    if name == "server_info":
        return {
            "ok": True,
            "data": {
                "server": "kicad-mcp-server",
                "version": "0.1.0",
                "pcbnew_available": PCBNEW_AVAILABLE,
            },
            "error": None,
        }

    if name == "get_board_state":
        return await loop.run_in_executor(None, bridge.get_board_state)

    if name == "new_board":
        return await loop.run_in_executor(
            None, lambda: bridge.new_board(
                path=args["path"],
                width_mm=args.get("width_mm", 100.0),
                height_mm=args.get("height_mm", 80.0),
            )
        )

    if name == "load_board":
        return await loop.run_in_executor(
            None, lambda: bridge.load_board(args["path"])
        )

    if name == "save_board":
        return await loop.run_in_executor(None, bridge.save_board)

    if name == "place_component":
        return await loop.run_in_executor(
            None, lambda: bridge.place_component(
                footprint_id=args["footprint_id"],
                ref=args["ref"],
                value=args["value"],
                x_mm=float(args["x_mm"]),
                y_mm=float(args["y_mm"]),
                rotation_deg=float(args.get("rotation_deg", 0.0)),
                layer=args.get("layer", "F.Cu"),
            )
        )

    if name == "move_component":
        return await loop.run_in_executor(
            None, lambda: bridge.move_component(
                ref=args["ref"],
                x_mm=float(args["x_mm"]),
                y_mm=float(args["y_mm"]),
                rotation_deg=args.get("rotation_deg"),
            )
        )

    if name == "delete_component":
        return await loop.run_in_executor(
            None, lambda: bridge.delete_component(ref=args["ref"])
        )

    if name == "add_trace":
        return await loop.run_in_executor(
            None, lambda: bridge.add_trace(
                net_name=args["net_name"],
                start_x_mm=float(args["start_x_mm"]),
                start_y_mm=float(args["start_y_mm"]),
                end_x_mm=float(args["end_x_mm"]),
                end_y_mm=float(args["end_y_mm"]),
                width_mm=float(args.get("width_mm", 0.25)),
                layer=args.get("layer", "F.Cu"),
            )
        )

    if name == "add_via":
        return await loop.run_in_executor(
            None, lambda: bridge.add_via(
                x_mm=float(args["x_mm"]),
                y_mm=float(args["y_mm"]),
                drill_mm=float(args.get("drill_mm", 0.3)),
                size_mm=float(args.get("size_mm", 0.6)),
                net_name=args.get("net_name", ""),
            )
        )

    if name == "run_drc":
        return await loop.run_in_executor(None, bridge.run_drc)

    return {"ok": False, "data": None, "error": f"Unknown tool: {name!r}"}


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    logger.info("KiCad MCP server starting (pcbnew_available=%s)", PCBNEW_AVAILABLE)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
