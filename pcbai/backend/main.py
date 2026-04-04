"""
PCB.AI FastAPI backend — entry point.
Runs on localhost:7842. Spawned as a child process by the Electron shell.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from claude_handler import ClaudeHandler
from kicad_mcp_client import KiCadMCPClient
from datasheet_parser import DatasheetParser
from export_handler import ExportHandler
from simulation import (
    PowerBudgetCalculator,
    TraceWidthCalculator,
    ImpedanceCalculator,
    SPICEGenerator,
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pcbai.backend")

# ── App state (singletons shared across requests) ─────────────────────────────

claude_handler: ClaudeHandler | None = None
kicad_client: KiCadMCPClient | None = None
datasheet_parser: DatasheetParser | None = None
export_handler: ExportHandler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global claude_handler, kicad_client, datasheet_parser, export_handler

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_handler = ClaudeHandler(api_key=api_key)
    kicad_client = KiCadMCPClient()
    datasheet_parser = DatasheetParser()
    export_handler = ExportHandler()

    logger.info("PCB.AI backend started on port 7842")
    yield

    # Graceful shutdown
    if kicad_client:
        await kicad_client.disconnect()
    logger.info("PCB.AI backend shut down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="PCB.AI Backend", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local-only desktop app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class SimulationRequest(BaseModel):
    circuit_type: str = "general"
    nets: list[dict] = []
    components: list[dict] = []


class ExportRequest(BaseModel):
    output_dir: str = ""
    formats: list[str] = ["gerbers", "drill", "bom", "pnp"]


class KiCadConnectRequest(BaseModel):
    board_path: str | None = None
    width_mm: float = 100.0
    height_mm: float = 80.0


class KiCadCommandRequest(BaseModel):
    tool: str
    args: dict = {}


class PlaceComponentRequest(BaseModel):
    footprint_id: str
    ref: str
    value: str
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0
    layer: str = "F.Cu"


class MoveComponentRequest(BaseModel):
    ref: str
    x_mm: float
    y_mm: float
    rotation_deg: float | None = None


class AddTraceRequest(BaseModel):
    net_name: str
    start_x_mm: float
    start_y_mm: float
    end_x_mm: float
    end_y_mm: float
    width_mm: float = 0.25
    layer: str = "F.Cu"


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — Electron polls this before showing the window."""
    return {"status": "ok", "version": "0.2.0"}


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint. Routes messages through ClaudeHandler.
    TODO (Step 3): Implement streaming SSE response.
    """
    response = await claude_handler.send_message(
        message=request.message,
        history=[m.model_dump() for m in request.history],
    )
    return {
        "message": response.get("content", ""),
        "expertise_level": response.get("expertise_level", "unknown"),
        "stage": response.get("stage", "intent_capture"),
    }


# ── KiCad ─────────────────────────────────────────────────────────────────────

@app.get("/kicad/status")
async def kicad_status():
    """Return current KiCad connection state and board summary."""
    return await kicad_client.get_status()


@app.post("/kicad/connect")
async def kicad_connect(request: KiCadConnectRequest):
    """
    Start the KiCad MCP server subprocess and connect to it.
    Optionally load an existing board or create a new one.
    """
    if kicad_client.connected:
        return {"ok": True, "message": "Already connected", "connected": True}

    success = await kicad_client.connect()
    if not success:
        raise HTTPException(status_code=503, detail="Failed to start KiCad MCP server. Check that the MCP server dependencies are installed.")

    # Load or create board
    if request.board_path:
        path = Path(request.board_path)
        if path.exists():
            result = await kicad_client.load_board(str(path))
        else:
            result = await kicad_client.new_board(
                str(path), request.width_mm, request.height_mm
            )
    else:
        result = {"ok": True, "message": "Connected. No board loaded yet."}

    return {
        "ok": success,
        "connected": kicad_client.connected,
        "board_result": result,
    }


@app.post("/kicad/disconnect")
async def kicad_disconnect():
    """Stop the KiCad MCP server."""
    await kicad_client.disconnect()
    return {"ok": True, "connected": False}


@app.post("/kicad/board/new")
async def kicad_new_board(request: KiCadConnectRequest):
    """Create a new board file."""
    if not request.board_path:
        raise HTTPException(status_code=400, detail="board_path is required")
    return await kicad_client.new_board(request.board_path, request.width_mm, request.height_mm)


@app.post("/kicad/board/load")
async def kicad_load_board(request: KiCadConnectRequest):
    """Load an existing .kicad_pcb file."""
    if not request.board_path:
        raise HTTPException(status_code=400, detail="board_path is required")
    return await kicad_client.load_board(request.board_path)


@app.get("/kicad/board")
async def kicad_board_state():
    """Return the current board state (component positions, traces, nets)."""
    return await kicad_client.get_board_state()


@app.post("/kicad/component/place")
async def kicad_place_component(request: PlaceComponentRequest):
    """Place a footprint on the board."""
    return await kicad_client.place_component(
        footprint_id=request.footprint_id,
        ref=request.ref,
        value=request.value,
        x_mm=request.x_mm,
        y_mm=request.y_mm,
        rotation_deg=request.rotation_deg,
        layer=request.layer,
    )


@app.post("/kicad/component/move")
async def kicad_move_component(request: MoveComponentRequest):
    """Move a component to new coordinates."""
    return await kicad_client.move_component(
        ref=request.ref,
        x_mm=request.x_mm,
        y_mm=request.y_mm,
        rotation_deg=request.rotation_deg,
    )


@app.post("/kicad/trace")
async def kicad_add_trace(request: AddTraceRequest):
    """Add a copper trace."""
    return await kicad_client.add_trace(
        net_name=request.net_name,
        start_x_mm=request.start_x_mm,
        start_y_mm=request.start_y_mm,
        end_x_mm=request.end_x_mm,
        end_y_mm=request.end_y_mm,
        width_mm=request.width_mm,
        layer=request.layer,
    )


@app.post("/kicad/drc")
async def kicad_run_drc():
    """Run DRC and return violations."""
    return await kicad_client.run_drc()


@app.post("/kicad/drc/reset")
async def kicad_reset_drc():
    """Reset the DRC iteration counter (call before starting a new DRC fix loop)."""
    kicad_client.reset_drc_iteration()
    return {"ok": True}


@app.post("/kicad/command")
async def kicad_command(request: KiCadCommandRequest):
    """
    Raw MCP tool call — for advanced use or debugging.
    Claude uses the specific endpoints above, not this one.
    """
    return await kicad_client.send_command(request.tool, request.args)


@app.post("/kicad/test")
async def kicad_test():
    """
    Integration test: connect → create a temp board → place R1 (220R 0805) → get state.
    Used during Step 2 verification.
    """
    import tempfile, os

    results = {}

    # 1. Connect
    if not kicad_client.connected:
        success = await kicad_client.connect()
        results["connect"] = {"ok": success}
        if not success:
            return {"ok": False, "results": results, "error": "Failed to connect"}
    else:
        results["connect"] = {"ok": True, "note": "already connected"}

    # 2. New temp board
    tmp = tempfile.mktemp(suffix=".kicad_pcb")
    new_result = await kicad_client.new_board(tmp, width_mm=50.0, height_mm=50.0)
    results["new_board"] = new_result

    # 3. Place a resistor at (25, 25)
    place_result = await kicad_client.place_component(
        footprint_id="Resistor_SMD:R_0805_2012Metric",
        ref="R1",
        value="220R",
        x_mm=25.0,
        y_mm=25.0,
        rotation_deg=0.0,
    )
    results["place_component"] = place_result

    # 4. Get board state
    state_result = await kicad_client.get_board_state()
    results["board_state"] = {
        "ok": state_result.get("ok"),
        "component_count": len((state_result.get("data") or {}).get("components", [])),
    }

    # Cleanup temp file
    try:
        os.unlink(tmp)
    except OSError:
        pass

    overall_ok = all(r.get("ok") for r in results.values())
    return {"ok": overall_ok, "results": results}


# ── Datasheet ─────────────────────────────────────────────────────────────────

@app.post("/datasheet/upload")
async def upload_datasheet(file: UploadFile = File(...)):
    """Accept a PDF datasheet and return extracted constraints. (Step 5)"""
    contents = await file.read()
    result = await datasheet_parser.parse(filename=file.filename, content=contents)
    return result


# ── Simulation ────────────────────────────────────────────────────────────────

@app.post("/simulation/run")
async def run_simulation(request: SimulationRequest):
    """Run Layer 1 fast simulation checks. (Step 6)"""
    results = []
    results.append(PowerBudgetCalculator().check(request.components))
    results.append(TraceWidthCalculator().check(request.nets))
    results.append(ImpedanceCalculator().check(request.nets))
    passed = all(r.get("passed", True) for r in results)
    return {"results": results, "passed": passed}


@app.post("/simulation/spice")
async def generate_spice(request: SimulationRequest):
    """Generate a SPICE netlist. (Step 6)"""
    netlist = SPICEGenerator().generate(
        circuit_type=request.circuit_type,
        components=request.components,
        nets=request.nets,
    )
    return {"netlist": netlist}


# ── Export ────────────────────────────────────────────────────────────────────

@app.post("/export")
async def export_board(request: ExportRequest):
    """Export fab files. (Step 10)"""
    files = await export_handler.export(
        output_dir=request.output_dir,
        formats=request.formats,
    )
    return {"files": files}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", 7842))
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        log_level="info",
    )
