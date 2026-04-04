"""
PCB.AI FastAPI backend — entry point.
Runs on localhost:7842. Spawned as a child process by the Electron shell.
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, UploadFile, File
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

    logger.info("PCB.AI backend shutting down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="PCB.AI Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local-only — acceptable for a desktop app
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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — Electron polls this before showing the window."""
    return {"status": "ok"}


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


@app.get("/kicad/status")
async def kicad_status():
    """Return current KiCad connection state and board summary."""
    status = await kicad_client.get_status()
    return status


@app.post("/kicad/command")
async def kicad_command(body: dict):
    """
    Send a raw command to KiCad via the MCP client.
    TODO (Step 2): Full command routing.
    """
    result = await kicad_client.send_command(body.get("command", ""), body.get("params", {}))
    return result


@app.post("/datasheet/upload")
async def upload_datasheet(file: UploadFile = File(...)):
    """
    Accept a PDF datasheet, parse it, and return extracted constraints.
    TODO (Step 5): Full PDF parsing and structured extraction.
    """
    contents = await file.read()
    result = await datasheet_parser.parse(filename=file.filename, content=contents)
    return result


@app.post("/simulation/run")
async def run_simulation(request: SimulationRequest):
    """
    Run Layer 1 fast simulation checks.
    TODO (Step 6): Full simulation engine.
    """
    results = []

    power_result = PowerBudgetCalculator().check(request.components)
    results.append(power_result)

    trace_result = TraceWidthCalculator().check(request.nets)
    results.append(trace_result)

    impedance_result = ImpedanceCalculator().check(request.nets)
    results.append(impedance_result)

    passed = all(r.get("passed", True) for r in results)
    return {"results": results, "passed": passed}


@app.post("/simulation/spice")
async def generate_spice(request: SimulationRequest):
    """Generate a SPICE netlist for the given circuit."""
    netlist = SPICEGenerator().generate(
        circuit_type=request.circuit_type,
        components=request.components,
        nets=request.nets,
    )
    return {"netlist": netlist}


@app.post("/export")
async def export_board(request: ExportRequest):
    """
    Export fab files (Gerbers, drill, BOM, pick-and-place).
    TODO (Step 10): Full export pipeline through KiCad.
    """
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
