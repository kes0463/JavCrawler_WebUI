import { useCallback, useLayoutEffect, useRef } from "react";

const BOTTOM_THRESHOLD_PX = 56;

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

/**
 * 스크롤 컨테이너가 맨 아래에 있을 때만 새 항목/높이 증가 시 자동 스크롤.
 * 사용자가 위로 올리면 멈추고, 다시 끝 근처로 오면 재개한다.
 */
export function useStickToBottomScroll<T>(items: T[], enabled = true) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  const updatePinned = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    pinnedRef.current = distanceFromBottom(el) <= BOTTOM_THRESHOLD_PX;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = containerRef.current;
    if (!el) return;
    pinnedRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  const stickIfPinned = useCallback(() => {
    if (!enabled) return;
    const el = containerRef.current;
    if (!el || !pinnedRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [enabled]);

  useLayoutEffect(() => {
    stickIfPinned();
  }, [items, stickIfPinned]);

  useLayoutEffect(() => {
    if (!enabled) return;
    scrollToBottom("auto");
  }, [enabled, scrollToBottom]);

  // items.length마다 RO를 재생성하지 않음 — 장시간 스트림에서 GC/레이아웃 비용 방지
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    const ro = new ResizeObserver(() => {
      stickIfPinned();
    });
    ro.observe(el);
    const child = el.firstElementChild;
    if (child) ro.observe(child);

    return () => ro.disconnect();
  }, [stickIfPinned]);

  return { containerRef, onScroll: updatePinned, scrollToBottom };
}
