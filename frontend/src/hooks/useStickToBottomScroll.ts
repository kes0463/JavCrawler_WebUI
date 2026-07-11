import { useCallback, useEffect, useRef } from "react";

const BOTTOM_THRESHOLD_PX = 48;

/**
 * 스크롤 컨테이너가 맨 아래에 붙어 있을 때만 새 항목 추가 시 자동 스크롤.
 * 사용자가 위로 스크롤하면 위치를 유지한다.
 */
export function useStickToBottomScroll<T>(items: T[], enabled = true) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  const updatePinned = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinnedRef.current = dist <= BOTTOM_THRESHOLD_PX;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = containerRef.current;
    if (!el) return;
    pinnedRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const el = containerRef.current;
    if (!el) return;
    if (pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [items, enabled]);

  useEffect(() => {
    if (enabled) scrollToBottom("auto");
  }, [enabled, scrollToBottom]);

  return { containerRef, onScroll: updatePinned, scrollToBottom };
}
