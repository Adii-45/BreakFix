/* WebSocket client for the live layer.

   Connects to the API Gateway WebSocket API (VITE_WS_URL) — or the local hub
   during development — and applies whatever the server pushes. There is no
   polling fallback that invents data: if the socket is down the UI keeps the
   last real state it received and says it is reconnecting. */
import { useCallback, useEffect, useRef, useState } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8001';
const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];

export function useRealtime(onPayload) {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  const attemptRef = useRef(0);
  const timerRef = useRef(null);
  const closedRef = useRef(false);
  const handlerRef = useRef(onPayload);
  handlerRef.current = onPayload;

  const connect = useCallback(() => {
    if (closedRef.current) return;
    let socket;
    try {
      socket = new WebSocket(WS_URL);
    } catch {
      scheduleReconnect();
      return;
    }
    socketRef.current = socket;

    socket.onopen = () => {
      attemptRef.current = 0;
      setConnected(true);
    };
    socket.onmessage = (event) => {
      try {
        handlerRef.current?.(JSON.parse(event.data));
      } catch { /* a frame we cannot parse is ignored, never rendered */ }
    };
    socket.onclose = () => {
      setConnected(false);
      scheduleReconnect();
    };
    socket.onerror = () => { try { socket.close(); } catch { /* already closing */ } };

    function scheduleReconnect() {
      if (closedRef.current) return;
      const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)];
      attemptRef.current += 1;
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(connect, delay);
    }
  }, []);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      clearTimeout(timerRef.current);
      try { socketRef.current?.close(); } catch { /* noop */ }
    };
  }, [connect]);

  /** Ask for a fresh snapshot (the $default route replies with one). */
  const refresh = useCallback(() => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ action: 'snapshot' }));
  }, []);

  return { connected, refresh, url: WS_URL };
}

export function relativeTime(epochSeconds) {
  if (!epochSeconds) return '';
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  if (delta < 10) return 'just now';
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}
