"""
Claude API handler.
Manages conversation history, system prompt, and API calls.
Full implementation in Step 3.
"""

import logging

logger = logging.getLogger("pcbai.claude_handler")


class ClaudeHandler:
    MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = None
        if api_key:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError:
                logger.warning("anthropic package not installed")

    async def send_message(self, message: str, history: list[dict]) -> dict:
        """
        Send a message to Claude and return the response.
        TODO (Step 3): Implement full conversation management, system prompt,
        streaming, and expertise-adaptive response formatting.
        """
        if not self._client:
            logger.warning("Claude client not initialized — returning stub response")
            return {
                "content": (
                    "Claude API not configured. Set ANTHROPIC_API_KEY in your .env file."
                ),
                "expertise_level": "unknown",
                "stage": "intent_capture",
            }

        # Stub: basic single-turn call
        messages = [*history, {"role": "user", "content": message}]
        response = await self._client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=messages,
        )
        return {
            "content": response.content[0].text,
            "expertise_level": "unknown",
            "stage": "intent_capture",
        }
