import { useState, useEffect } from 'react';

/**
 * Hook for reading live KiCad board state.
 * Currently a stub — full implementation comes in Step 2 (KiCad MCP connection).
 */
export function useKiCadState() {
  const [boardState, setBoardState] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // TODO (Step 2): Poll /kicad/status and subscribe to kicad:update IPC events
    let cancelled = false;

    async function checkStatus() {
      try {
        const res = await fetch('http://localhost:7842/kicad/status');
        if (res.ok && !cancelled) {
          const data = await res.json();
          setIsConnected(data.connected ?? false);
          setBoardState(data.board ?? null);
        }
      } catch {
        // Backend not yet running — expected during initial load
      }
    }

    checkStatus();
    const interval = setInterval(checkStatus, 5000);

    // Also listen for real-time push updates via Electron IPC
    if (window.pcbai?.onKiCadUpdate) {
      window.pcbai.onKiCadUpdate((data) => {
        if (!cancelled) {
          setBoardState(data);
          setIsConnected(true);
        }
      });
    }

    return () => {
      cancelled = true;
      clearInterval(interval);
      window.pcbai?.offKiCadUpdate?.();
    };
  }, []);

  return { boardState, isConnected };
}
