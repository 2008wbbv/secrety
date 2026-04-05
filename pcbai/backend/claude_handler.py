"""
claude_handler.py
-----------------
Manages all Claude API interactions:
  - Streaming message generation via SSE
  - Per-session conversation history
  - System prompt rebuilding based on detected expertise and stage
  - Parsing _meta blocks from Claude responses to track state
  - Expertise detection + stage progression

Session state lives in memory (sufficient for a single-user desktop app).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import AsyncIterator

from system_prompt import (
    ExpertiseLevel,
    Stage,
    build_system_prompt,
)
from expertise_detector import ExpertiseDetector

logger = logging.getLogger("pcbai.claude_handler")

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

# ── Meta block parser ─────────────────────────────────────────────────────────

_META_PATTERN = re.compile(
    r'\{"_meta":\s*\{.*?\}\s*\}',
    re.DOTALL,
)


def _extract_meta(text: str) -> tuple[str, dict]:
    """
    Strip the _meta JSON block from Claude's response and parse it.
    Returns (clean_text, meta_dict).
    """
    match = _META_PATTERN.search(text)
    if not match:
        return text, {}

    try:
        meta_wrapper = json.loads(match.group(0))
        meta = meta_wrapper.get("_meta", {})
    except json.JSONDecodeError:
        meta = {}

    clean = text[: match.start()].rstrip() + text[match.end() :]
    return clean.strip(), meta


# ── Session ───────────────────────────────────────────────────────────────────

class Session:
    """Per-user conversation state."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: list[dict] = []          # [{"role": "user"|"assistant", "content": str}]
        self.expertise_level: ExpertiseLevel = "unknown"
        self.stage: Stage = "intent_capture"
        self.decisions: list[str] = []         # Accumulated autonomous decisions
        self.board_state: dict | None = None   # Injected from KiCad before each call
        self._detector = ExpertiseDetector()   # Local heuristic; refined by Claude's _meta

    def add_user_message(self, content: str):
        # Run local detector on every user message so the system prompt has a
        # best-guess before Claude even responds.
        analysis = self._detector.analyze(content)
        detector_level = self._detector.level()

        # Local detector only upgrades from "unknown"; Claude's _meta can override
        if self.expertise_level == "unknown" and detector_level != "unknown":
            logger.info(
                "[%s] Expertise pre-classified by detector: %s (conf=%.2f)",
                self.session_id, detector_level, self._detector.confidence(),
            )
            self.expertise_level = detector_level

        self.history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.history.append({"role": "assistant", "content": content})

    def update_from_meta(self, meta: dict):
        if "expertise_level" in meta:
            new_level = meta["expertise_level"]
            if new_level in ("beginner", "expert", "mixed", "unknown"):
                if new_level != self.expertise_level:
                    logger.info(
                        "[%s] Expertise updated: %s → %s",
                        self.session_id, self.expertise_level, new_level,
                    )
                self.expertise_level = new_level

        if "stage" in meta:
            new_stage = meta["stage"]
            if new_stage != self.stage:
                logger.info(
                    "[%s] Stage advanced: %s → %s",
                    self.session_id, self.stage, new_stage,
                )
            self.stage = new_stage

        if "decisions" in meta and isinstance(meta["decisions"], list):
            self.decisions.extend(meta["decisions"])

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "expertise_level": self.expertise_level,
            "stage": self.stage,
            "message_count": len(self.history),
            "decisions": self.decisions,
            "detector": self._detector.summary(),
        }


# ── ClaudeHandler ─────────────────────────────────────────────────────────────

class ClaudeHandler:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None
        self._sessions: dict[str, Session] = {}

        if api_key:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
                logger.info("Anthropic client initialized (model=%s)", MODEL)
            except ImportError:
                logger.warning("anthropic package not installed — Claude calls will be stubbed")
        else:
            logger.warning("ANTHROPIC_API_KEY not set — Claude calls will be stubbed")

    # ── Session management ────────────────────────────────────────────────────

    def get_or_create_session(self, session_id: str | None = None) -> Session:
        if session_id is None:
            session_id = str(uuid.uuid4())
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id)
            logger.info("New session created: %s", session_id)
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> dict:
        if session_id in self._sessions:
            del self._sessions[session_id]
        new_session = self.get_or_create_session(session_id)
        return new_session.to_dict()

    def get_session_info(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        return session.to_dict() if session else None

    def inject_board_state(self, session_id: str, board_state: dict | None):
        """Called by KiCad client after board operations to keep context current."""
        session = self._sessions.get(session_id)
        if session:
            session.board_state = board_state

    # ── Streaming response ────────────────────────────────────────────────────

    async def stream_message(
        self,
        message: str,
        session_id: str,
        board_state: dict | None = None,
    ) -> AsyncIterator[str]:
        """
        Yield SSE-formatted lines for the frontend.

        SSE event types:
          data: {"type": "text", "text": "..."}          — partial text chunk
          data: {"type": "meta", ...}                     — session state update
          data: {"type": "done"}                          — stream complete
          data: {"type": "error", "error": "..."}        — error occurred
        """
        session = self.get_or_create_session(session_id)
        if board_state:
            session.board_state = board_state

        session.add_user_message(message)

        if not self._client:
            # Stub mode — yield a single response
            stub_text = self._stub_response(message, session)
            session.add_assistant_message(stub_text)
            yield _sse({"type": "text", "text": stub_text})
            yield _sse({
                "type": "meta",
                "expertise_level": session.expertise_level,
                "stage": session.stage,
                "session_id": session_id,
            })
            yield _sse({"type": "done"})
            return

        # Build system prompt for current state
        system_prompt = build_system_prompt(
            expertise_level=session.expertise_level,
            stage=session.stage,
            board_state=session.board_state,
        )

        # Stream from Claude
        full_response = ""
        try:
            async with self._client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=session.history,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    full_response += text_chunk
                    yield _sse({"type": "text", "text": text_chunk})

        except Exception as exc:
            logger.error("[%s] Claude API error: %s", session_id, exc)
            yield _sse({"type": "error", "error": str(exc)})
            yield _sse({"type": "done"})
            return

        # Parse _meta block, update session state
        clean_text, meta = _extract_meta(full_response)

        # If Claude included _meta, update session; otherwise keep current state
        if meta:
            session.update_from_meta(meta)

        # Store the clean response (without _meta) in history
        session.add_assistant_message(clean_text)

        # Send session state update to frontend
        yield _sse({
            "type": "meta",
            "expertise_level": session.expertise_level,
            "stage": session.stage,
            "session_id": session_id,
            "decisions": meta.get("decisions", []),
        })
        yield _sse({"type": "done"})

    # ── Non-streaming (for internal use by the agentic loop) ─────────────────

    async def send_message(
        self,
        message: str,
        history: list[dict] | None = None,
        session_id: str | None = None,
        board_state: dict | None = None,
    ) -> dict:
        """
        Non-streaming version — returns full response dict.
        Used by the KiCad agentic loop (Step 7) where streaming is not needed.
        """
        session = self.get_or_create_session(session_id)
        if board_state:
            session.board_state = board_state

        if not self._client:
            return {
                "content": self._stub_response(message, session),
                "expertise_level": session.expertise_level,
                "stage": session.stage,
                "session_id": session.session_id,
            }

        system_prompt = build_system_prompt(
            expertise_level=session.expertise_level,
            stage=session.stage,
            board_state=session.board_state,
        )

        messages = history or session.history
        if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != message:
            messages = [*messages, {"role": "user", "content": message}]

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )

        full_text = response.content[0].text
        clean_text, meta = _extract_meta(full_text)

        if meta:
            session.update_from_meta(meta)

        return {
            "content": clean_text,
            "expertise_level": session.expertise_level,
            "stage": session.stage,
            "session_id": session.session_id,
            "decisions": meta.get("decisions", []),
        }

    # ── Stub ──────────────────────────────────────────────────────────────────

    def _stub_response(self, message: str, session: Session) -> str:
        """Returned when ANTHROPIC_API_KEY is not configured."""
        return (
            f"[PCB.AI — API key not configured]\n\n"
            f"Set ANTHROPIC_API_KEY in your .env file to enable Claude.\n\n"
            f"Your message: \"{message}\"\n"
            f"Session: {session.session_id[:8]}... | "
            f"Stage: {session.stage} | "
            f"Expertise: {session.expertise_level}"
        )


# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"
