import { useState, useEffect } from 'react';

/**
 * Hook for reading live KiCad board state.
 * Polls /kicad/status every 5s and subscribes to Electron IPC push events.
 */
export function useKiCadState() {
  const [boardState, setBoardState] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [queueDepth, setQueueDepth] = useState(0);
  const [drcIteration, setDrcIteration] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function checkStatus() {
      try {
        const res = await fetch('http://localhost:7842/kicad/status');
        if (res.ok && !cancelled) {
          const data = await res.json();
          setIsConnected(data.connected ?? false);
          setBoardState(data.board ?? null);
          setQueueDepth(data.queue_depth ?? 0);
          setDrcIteration(data.drc_iteration ?? 0);
        }
      } catch {
        // Backend not yet running
      }
    }

    checkStatus();
    const interval = setInterval(checkStatus, 5000);

    // Listen for real-time push updates via Electron IPC (Step 2+)
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

  return { boardState, isConnected, queueDepth, drcIteration };
}
