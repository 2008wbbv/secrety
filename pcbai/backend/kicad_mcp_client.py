"""
kicad_mcp_client.py
-------------------
Manages the lifecycle of the KiCad MCP server subprocess and provides
a high-level async API for the FastAPI routes to use.

Key design decisions (from spec):
  1. Command queue — commands are processed one at a time.
     Claude can generate commands faster than KiCad can process them.
     Each command waits for acknowledgment before the next is dispatched.
  2. Reconnection — the MCP server subprocess can crash or disconnect.
     The client re-spawns it automatically and retries the failing command.
  3. Board state cache — after every mutating command the board state is
     re-fetched and cached so the FastAPI /kicad/board endpoint is always fast.
  4. DRC loop guard — run_drc tracks iteration count and surfaces unresolved
     violations after MAX_DRC_ITERATIONS attempts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("pcbai.kicad_mcp_client")

# ── Constants ─────────────────────────────────────────────────────────────────

MCP_SERVER_DIR = Path(__file__).parent.parent / "mcp" / "kicad-mcp-server"
MCP_SERVER_SCRIPT = MCP_SERVER_DIR / "server.py"

COMMAND_TIMEOUT_S = 30       # Per-command timeout
RECONNECT_DELAY_S = 2.0      # Delay before reconnect attempt
MAX_RECONNECT_ATTEMPTS = 5
MAX_DRC_ITERATIONS = 10      # Guard against infinite DRC fix loops


# ── MCP stdio JSON-RPC transport ──────────────────────────────────────────────

class MCPTransport:
    """
    Minimal JSON-RPC 2.0 over stdio transport for the MCP server.

    Manages the subprocess and provides send/receive primitives.
    """

    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._initialized = False

    async def start(self) -> bool:
        """Launch the MCP server subprocess. Returns True on success."""
        if not MCP_SERVER_SCRIPT.exists():
            logger.error("MCP server script not found: %s", MCP_SERVER_SCRIPT)
            return False

        try:
            self._proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(MCP_SERVER_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(MCP_SERVER_DIR),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            logger.info("MCP server subprocess started (pid=%d)", self._proc.pid)

            # Log stderr in background
            asyncio.create_task(self._drain_stderr())

            # Start the response reader loop
            self._reader_task = asyncio.create_task(self._read_loop())

            # MCP initialize handshake
            await self._initialize()
            return True

        except Exception as exc:
            logger.error("Failed to start MCP server: %s", exc)
            return False

    async def stop(self):
        """Terminate the MCP server subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
        self._initialized = False
        # Fail all pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("MCP server stopped"))
        self._pending.clear()

    @property
    def alive(self) -> bool:
        return (
            self._proc is not None
            and self._proc.returncode is None
            and self._initialized
        )

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return the parsed result dict."""
        if not self.alive:
            raise ConnectionError("MCP server not connected")

        msg_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._send(payload)

        try:
            response = await asyncio.wait_for(fut, timeout=COMMAND_TIMEOUT_S)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"Tool call '{tool_name}' timed out after {COMMAND_TIMEOUT_S}s")

        # MCP returns content list; extract the first TextContent item
        content = response.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return {"ok": False, "data": None, "error": "Invalid JSON in tool response"}
        return {"ok": False, "data": None, "error": f"Unexpected response format: {response}"}

    # ── Private ───────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _send(self, payload: dict):
        line = json.dumps(payload) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()

    async def _initialize(self):
        """Perform MCP initialize/initialized handshake."""
        msg_id = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        await self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "pcbai-backend", "version": "0.1.0"},
            },
        })

        try:
            await asyncio.wait_for(fut, timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError("MCP initialization timed out")

        # Send initialized notification (no response expected)
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._initialized = True
        logger.info("MCP server initialized")

    async def _read_loop(self):
        """Background task: read JSON-RPC responses from server stdout."""
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    logger.warning("MCP server stdout closed")
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON from MCP server: %s", line[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(str(msg["error"])))
                        else:
                            fut.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("MCP read loop error: %s", exc)

    async def _drain_stderr(self):
        """Log MCP server stderr for debugging."""
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                logger.debug("[mcp-server] %s", line.decode().rstrip())
        except asyncio.CancelledError:
            pass


# ── Command Queue ─────────────────────────────────────────────────────────────

class CommandQueueItem:
    __slots__ = ("tool", "args", "future")

    def __init__(self, tool: str, args: dict):
        self.tool = tool
        self.args = args
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


# ── KiCadMCPClient ────────────────────────────────────────────────────────────

class KiCadMCPClient:
    """
    High-level async client used by FastAPI route handlers.

    Provides:
      - Subprocess lifecycle (start/stop/reconnect)
      - Async command queue (one command at a time, ACK before next)
      - Board state cache (refreshed after every mutation)
      - DRC loop with iteration guard
    """

    def __init__(self):
        self._transport = MCPTransport()
        self._queue: asyncio.Queue[CommandQueueItem] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._board_state_cache: dict | None = None
        self._reconnect_attempts = 0
        self._drc_iteration = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Start the MCP server and command queue worker."""
        success = await self._transport.start()
        if success:
            self._worker_task = asyncio.create_task(self._queue_worker())
            self._reconnect_attempts = 0
            logger.info("KiCadMCPClient connected")
        return success

    async def disconnect(self):
        """Stop the command queue and MCP server."""
        if self._worker_task:
            self._worker_task.cancel()
        await self._transport.stop()
        logger.info("KiCadMCPClient disconnected")

    async def reconnect(self) -> bool:
        """Reconnect after a connection drop."""
        if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            logger.error("Max reconnect attempts (%d) reached", MAX_RECONNECT_ATTEMPTS)
            return False
        self._reconnect_attempts += 1
        logger.info("Reconnecting (attempt %d/%d)...", self._reconnect_attempts, MAX_RECONNECT_ATTEMPTS)
        await asyncio.sleep(RECONNECT_DELAY_S * self._reconnect_attempts)
        await self._transport.stop()
        self._transport = MCPTransport()
        success = await self._transport.start()
        if success:
            self._reconnect_attempts = 0
            if not self._worker_task or self._worker_task.done():
                self._worker_task = asyncio.create_task(self._queue_worker())
        return success

    @property
    def connected(self) -> bool:
        return self._transport.alive

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "board": self._board_state_cache,
            "queue_depth": self._queue.qsize(),
            "drc_iteration": self._drc_iteration,
        }

    async def send_command(self, tool: str, args: dict) -> dict:
        """
        Queue a command and await its result.
        Blocks until the command is processed (one at a time).
        """
        if not self.connected:
            return {"ok": False, "data": None, "error": "KiCad MCP server not connected. Call /kicad/connect first."}

        item = CommandQueueItem(tool, args)
        await self._queue.put(item)
        try:
            return await asyncio.wait_for(item.future, timeout=COMMAND_TIMEOUT_S + 5)
        except asyncio.TimeoutError:
            return {"ok": False, "data": None, "error": f"Command '{tool}' timed out in queue"}

    async def place_component(
        self,
        footprint_id: str,
        ref: str,
        value: str,
        x_mm: float,
        y_mm: float,
        rotation_deg: float = 0.0,
        layer: str = "F.Cu",
    ) -> dict:
        result = await self.send_command("place_component", {
            "footprint_id": footprint_id,
            "ref": ref,
            "value": value,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "rotation_deg": rotation_deg,
            "layer": layer,
        })
        if result.get("ok"):
            await self._refresh_board_state()
        return result

    async def move_component(self, ref: str, x_mm: float, y_mm: float, rotation_deg: float | None = None) -> dict:
        args = {"ref": ref, "x_mm": x_mm, "y_mm": y_mm}
        if rotation_deg is not None:
            args["rotation_deg"] = rotation_deg
        result = await self.send_command("move_component", args)
        if result.get("ok"):
            await self._refresh_board_state()
        return result

    async def add_trace(
        self,
        net_name: str,
        start_x_mm: float,
        start_y_mm: float,
        end_x_mm: float,
        end_y_mm: float,
        width_mm: float = 0.25,
        layer: str = "F.Cu",
    ) -> dict:
        result = await self.send_command("add_trace", {
            "net_name": net_name,
            "start_x_mm": start_x_mm,
            "start_y_mm": start_y_mm,
            "end_x_mm": end_x_mm,
            "end_y_mm": end_y_mm,
            "width_mm": width_mm,
            "layer": layer,
        })
        if result.get("ok"):
            await self._refresh_board_state()
        return result

    async def run_drc(self) -> dict:
        """
        Run DRC. Tracks iteration count.
        Returns violations and whether the guard limit was hit.
        """
        self._drc_iteration += 1
        hit_limit = self._drc_iteration >= MAX_DRC_ITERATIONS

        result = await self.send_command("run_drc", {})
        if result.get("ok"):
            result["data"]["drc_iteration"] = self._drc_iteration
            result["data"]["hit_iteration_limit"] = hit_limit
            if hit_limit:
                result["data"]["note"] = (
                    f"DRC iteration limit ({MAX_DRC_ITERATIONS}) reached. "
                    "Remaining violations must be resolved manually."
                )
        return result

    def reset_drc_iteration(self):
        """Call when starting a new DRC loop (e.g., after user approves a new layout)."""
        self._drc_iteration = 0

    async def get_board_state(self) -> dict:
        """Return the cached board state, or fetch fresh if cache is empty."""
        if self._board_state_cache is None:
            await self._refresh_board_state()
        return {
            "ok": True,
            "data": self._board_state_cache,
            "error": None,
        }

    async def new_board(self, path: str, width_mm: float = 100.0, height_mm: float = 80.0) -> dict:
        result = await self.send_command("new_board", {"path": path, "width_mm": width_mm, "height_mm": height_mm})
        if result.get("ok"):
            self.reset_drc_iteration()
            await self._refresh_board_state()
        return result

    async def load_board(self, path: str) -> dict:
        result = await self.send_command("load_board", {"path": path})
        if result.get("ok"):
            self.reset_drc_iteration()
            await self._refresh_board_state()
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    async def _queue_worker(self):
        """
        Process one command at a time. Wait for ACK before taking the next.
        Handles reconnection if the server drops mid-queue.
        """
        logger.info("Command queue worker started")
        while True:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                break

            if item.future.done():
                # Cancelled by caller before we got to it
                self._queue.task_done()
                continue

            try:
                result = await self._call_with_reconnect(item.tool, item.args)
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as exc:
                if not item.future.done():
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()

    async def _call_with_reconnect(self, tool: str, args: dict) -> dict:
        """Try the tool call; reconnect and retry once if it fails."""
        if not self._transport.alive:
            logger.warning("Transport not alive before command '%s', reconnecting...", tool)
            if not await self.reconnect():
                return {"ok": False, "data": None, "error": "Cannot reconnect to MCP server"}

        try:
            return await self._transport.call_tool(tool, args)
        except (ConnectionError, TimeoutError) as exc:
            logger.warning("Command '%s' failed (%s), attempting reconnect...", tool, exc)
            if await self.reconnect():
                return await self._transport.call_tool(tool, args)
            return {"ok": False, "data": None, "error": f"Command failed and reconnect failed: {exc}"}

    async def _refresh_board_state(self):
        """Fetch and cache the current board state."""
        try:
            result = await self._transport.call_tool("get_board_state", {})
            if result.get("ok"):
                self._board_state_cache = result.get("data")
        except Exception as exc:
            logger.warning("Failed to refresh board state: %s", exc)
