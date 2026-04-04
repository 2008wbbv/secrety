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
from fastapi.responses import StreamingResponse
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

# ── Singletons ────────────────────────────────────────────────────────────────

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

    if kicad_client:
        await kicad_client.disconnect()
    logger.info("PCB.AI backend shut down")


app = FastAPI(title="PCB.AI Backend", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SessionResetRequest(BaseModel):
    session_id: str


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
    return {"status": "ok", "version": "0.3.0"}


# ── Chat (streaming SSE) ──────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Streaming chat endpoint. Returns Server-Sent Events.

    SSE event types:
      data: {"type": "text", "text": "..."}    — token chunk
      data: {"type": "meta", ...}               — session state (expertise, stage)
      data: {"type": "done"}                    — stream complete
      data: {"type": "error", "error": "..."}  — error

    The frontend must read this as a stream using fetch() with a ReadableStream
    reader, not EventSource (because we send POST not GET).
    """
    board_state = None
    if kicad_client and kicad_client.connected:
        board_result = await kicad_client.get_board_state()
        board_state = board_result.get("data")

    return StreamingResponse(
        claude_handler.stream_message(
            message=request.message,
            session_id=request.session_id,
            board_state=board_state,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/chat/session/{session_id}")
async def get_session(session_id: str):
    """Return session metadata (expertise level, stage, message count)."""
    info = claude_handler.get_session_info(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return info


@app.post("/chat/reset")
async def reset_session(request: SessionResetRequest):
    """Reset a conversation session to start fresh."""
    return claude_handler.reset_session(request.session_id)


# ── KiCad ─────────────────────────────────────────────────────────────────────

@app.get("/kicad/status")
async def kicad_status():
    return await kicad_client.get_status()


@app.post("/kicad/connect")
async def kicad_connect(request: KiCadConnectRequest):
    if kicad_client.connected:
        return {"ok": True, "message": "Already connected", "connected": True}

    success = await kicad_client.connect()
    if not success:
        raise HTTPException(status_code=503, detail="Failed to start KiCad MCP server")

    result = {"ok": success, "connected": kicad_client.connected}

    if request.board_path:
        p = Path(request.board_path)
        board_result = (
            await kicad_client.load_board(str(p))
            if p.exists()
            else await kicad_client.new_board(str(p), request.width_mm, request.height_mm)
        )
        result["board_result"] = board_result

    return result


@app.post("/kicad/disconnect")
async def kicad_disconnect():
    await kicad_client.disconnect()
    return {"ok": True, "connected": False}


@app.post("/kicad/board/new")
async def kicad_new_board(request: KiCadConnectRequest):
    if not request.board_path:
        raise HTTPException(status_code=400, detail="board_path required")
    return await kicad_client.new_board(request.board_path, request.width_mm, request.height_mm)


@app.post("/kicad/board/load")
async def kicad_load_board(request: KiCadConnectRequest):
    if not request.board_path:
        raise HTTPException(status_code=400, detail="board_path required")
    return await kicad_client.load_board(request.board_path)


@app.get("/kicad/board")
async def kicad_board_state():
    return await kicad_client.get_board_state()


@app.post("/kicad/component/place")
async def kicad_place_component(request: PlaceComponentRequest):
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
    return await kicad_client.move_component(
        ref=request.ref,
        x_mm=request.x_mm,
        y_mm=request.y_mm,
        rotation_deg=request.rotation_deg,
    )


@app.post("/kicad/trace")
async def kicad_add_trace(request: AddTraceRequest):
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
    return await kicad_client.run_drc()


@app.post("/kicad/drc/reset")
async def kicad_reset_drc():
    kicad_client.reset_drc_iteration()
    return {"ok": True}


@app.post("/kicad/command")
async def kicad_command(request: KiCadCommandRequest):
    return await kicad_client.send_command(request.tool, request.args)


@app.post("/kicad/test")
async def kicad_test():
    """Integration test: connect → new board → place R1 220R → get state."""
    import tempfile

    results = {}

    if not kicad_client.connected:
        success = await kicad_client.connect()
        results["connect"] = {"ok": success}
        if not success:
            return {"ok": False, "results": results, "error": "Failed to connect"}
    else:
        results["connect"] = {"ok": True, "note": "already connected"}

    tmp = tempfile.mktemp(suffix=".kicad_pcb")
    results["new_board"] = await kicad_client.new_board(tmp, width_mm=50.0, height_mm=50.0)

    results["place_component"] = await kicad_client.place_component(
        footprint_id="Resistor_SMD:R_0805_2012Metric",
        ref="R1",
        value="220R",
        x_mm=25.0,
        y_mm=25.0,
    )

    state_result = await kicad_client.get_board_state()
    results["board_state"] = {
        "ok": state_result.get("ok"),
        "component_count": len((state_result.get("data") or {}).get("components", [])),
    }

    try:
        import os
        os.unlink(tmp)
    except OSError:
        pass

    return {"ok": all(r.get("ok") for r in results.values()), "results": results}


# ── Datasheet ─────────────────────────────────────────────────────────────────

@app.post("/datasheet/upload")
async def upload_datasheet(file: UploadFile = File(...)):
    contents = await file.read()
    return await datasheet_parser.parse(filename=file.filename, content=contents)


# ── Simulation ────────────────────────────────────────────────────────────────

@app.post("/simulation/run")
async def run_simulation(request: SimulationRequest):
    results = [
        PowerBudgetCalculator().check(request.components),
        TraceWidthCalculator().check(request.nets),
        ImpedanceCalculator().check(request.nets),
    ]
    return {"results": results, "passed": all(r.get("passed", True) for r in results)}


@app.post("/simulation/spice")
async def generate_spice(request: SimulationRequest):
    return {
        "netlist": SPICEGenerator().generate(
            circuit_type=request.circuit_type,
            components=request.components,
            nets=request.nets,
        )
    }


# ── Export ────────────────────────────────────────────────────────────────────

@app.post("/export")
async def export_board(request: ExportRequest):
    files = await export_handler.export(output_dir=request.output_dir, formats=request.formats)
    return {"files": files}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", 7842))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=False, log_level="info")
