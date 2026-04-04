import { useState, useCallback } from 'react';

/**
 * Hook for sending messages to the Claude backend and receiving streamed responses.
 * Currently a stub — full streaming implementation comes in Step 3 (Claude API integration).
 */
export function useClaudeStream() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = useCallback(async (text) => {
    const userMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    setIsStreaming(true);

    try {
      // TODO (Step 3): Replace with real streaming fetch to /chat
      const response = await fetch('http://localhost:7842/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: messages }),
      });

      if (response.ok) {
        const data = await response.json();
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.message ?? '(no response)' },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${response.status}` },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Connection error: ${err.message}` },
      ]);
    } finally {
      setIsStreaming(false);
    }
  }, [messages]);

  return { messages, isStreaming, sendMessage };
}
