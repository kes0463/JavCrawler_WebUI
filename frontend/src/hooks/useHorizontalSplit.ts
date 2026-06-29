import { useCallback, useEffect, useRef, useState } from "react";

interface UseHorizontalSplitOptions {
  initialWidth: number;
  minWidth: number;
  maxWidth: number;
  storageKey?: string;
}

export function useHorizontalSplit({
  initialWidth,
  minWidth,
  maxWidth,
  storageKey,
}: UseHorizontalSplitOptions) {
  const [width, setWidth] = useState(() => {
    if (storageKey && typeof window !== "undefined") {
      const saved = Number(localStorage.getItem(storageKey));
      if (!Number.isNaN(saved) && saved >= minWidth && saved <= maxWidth) {
        return saved;
      }
    }
    return initialWidth;
  });
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(width);
  const captureTarget = useRef<HTMLElement | null>(null);
  const capturePointerId = useRef<number | null>(null);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = width;
    captureTarget.current = e.currentTarget as HTMLElement;
    capturePointerId.current = e.pointerId;
    captureTarget.current.setPointerCapture(e.pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [width]);

  useEffect(() => {
    const onPointerMove = (e: PointerEvent) => {
      if (!dragging.current) return;
      const next = Math.min(maxWidth, Math.max(minWidth, startWidth.current + e.clientX - startX.current));
      setWidth(next);
    };
    const onPointerUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      if (captureTarget.current && capturePointerId.current !== null) {
        try {
          captureTarget.current.releasePointerCapture(capturePointerId.current);
        } catch {
          /* ignore */
        }
      }
      captureTarget.current = null;
      capturePointerId.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [minWidth, maxWidth]);

  useEffect(() => {
    if (storageKey) localStorage.setItem(storageKey, String(width));
  }, [width, storageKey]);

  return { width, onPointerDown };
}
