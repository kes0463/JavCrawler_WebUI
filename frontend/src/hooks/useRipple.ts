import { useState, useCallback, useRef, useEffect } from "react";

// Must match the CSS animation duration defined in tailwind.config.js
const RIPPLE_DURATION_MS = 550;

interface Ripple {
  id: number;
  x: number;
  y: number;
  size: number;
}

export function useRipple() {
  const [ripples, setRipples] = useState<Ripple[]>([]);
  const pendingTimers = useRef(new Set<ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const { current } = pendingTimers;
    return () => current.forEach(clearTimeout);
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const id = Date.now() + Math.random();

    setRipples(prev => [
      ...prev,
      { id, x: e.clientX - rect.left - size / 2, y: e.clientY - rect.top - size / 2, size },
    ]);

    const tid = setTimeout(() => {
      setRipples(prev => prev.filter(r => r.id !== id));
      pendingTimers.current.delete(tid);
    }, RIPPLE_DURATION_MS);
    pendingTimers.current.add(tid);
  }, []);

  return { ripples, onMouseDown };
}
