import { useState, useCallback, useRef } from 'react';

const BACKEND_URL = 'http://127.0.0.1:7842';

/**
 * Hook for streaming Claude responses via SSE over a POST /chat request.
 *
 * The backend returns Server-Sent Events:
 *   data: {"type": "text", "text": "..."}     — token chunk
 *   data: {"type": "meta", ...}               — expertise/stage update
 *   data: {"type": "done"}                    — stream complete
 *   data: {"type": "error", "error": "..."}  — error
 *
 * We use fetch() + ReadableStream rather than EventSource because EventSource
 * only supports GET requests.
 */
export function useClaudeStream() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [expertiseLevel, setExpertiseLevel] = useState('unknown');
  const [stage, setStage] = useState('intent_capture');

  // Abort controller so the user can cancel a streaming response
  const abortRef = useRef(null);

  const sendMessage = useCallback(async (text) => {
    if (isStreaming) return;

    const userMsg = { role: 'user', content: text, id: Date.now() };
    const assistantMsgId = Date.now() + 1;
    const assistantMsg = { role: 'assistant', content: '', id: assistantMsgId, streaming: true };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);
    setError(null);

    abortRef.current = new AbortController();

    try {
      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE lines are separated by \n\n; process all complete events
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? ''; // Keep incomplete trailing chunk

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;

          let event;
          try {
            event = JSON.parse(line.slice(6));
          } catch (e) {
            console.warn('[useClaudeStream] Failed to parse SSE line:', line, e);
            continue;
          }

          if (event.type === 'text') {
            // Append token to the streaming assistant message
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: m.content + event.text }
                  : m
              )
            );
          } else if (event.type === 'meta') {
            // Update session state
            if (event.session_id) setSessionId(event.session_id);
            if (event.expertise_level) setExpertiseLevel(event.expertise_level);
            if (event.stage) setStage(event.stage);
          } else if (event.type === 'error') {
            throw new Error(event.error);
          } else if (event.type === 'done') {
            // Mark assistant message as no longer streaming
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, streaming: false } : m
              )
            );
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // User cancelled — mark the partial message as done
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, streaming: false, content: m.content + ' [cancelled]' }
              : m
          )
        );
      } else {
        setError(err.message);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, streaming: false, content: `Error: ${err.message}` }
              : m
          )
        );
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, [isStreaming, sessionId]);

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    isStreaming,
    error,
    sessionId,
    expertiseLevel,
    stage,
    sendMessage,
    cancelStream,
    clearMessages,
  };
}
