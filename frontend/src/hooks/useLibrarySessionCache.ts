import { useCallback, useEffect, useRef } from "react";
import type { LibraryItem, LibraryQuery } from "@/api/library";

const STORAGE_KEY = "javstory.library.list.v1";
const MAX_BYTES = 1_500_000;
const TRIM_ITEMS = 128;
const STALE_MS = 5 * 60 * 1000;

export interface LibrarySessionSnapshot {
  query: LibraryQuery;
  items: LibraryItem[];
  total: number;
  scrollTop: number;
  savedAt: number;
}

function queryKey(q: LibraryQuery): string {
  const { page: _page, ...rest } = q;
  return JSON.stringify(rest);
}

function readRaw(): LibrarySessionSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LibrarySessionSnapshot;
    if (!parsed || !Array.isArray(parsed.items) || typeof parsed.total !== "number") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function trimForStorage(snapshot: LibrarySessionSnapshot): LibrarySessionSnapshot {
  let payload = snapshot;
  let serialized = JSON.stringify(payload);
  if (serialized.length <= MAX_BYTES) return payload;

  payload = {
    ...snapshot,
    items: snapshot.items.slice(-TRIM_ITEMS),
  };
  serialized = JSON.stringify(payload);
  if (serialized.length <= MAX_BYTES) return payload;

  return {
    ...payload,
    items: snapshot.items.slice(-Math.min(64, TRIM_ITEMS)),
  };
}

export function loadLibrarySession(): LibrarySessionSnapshot | null {
  return readRaw();
}

export function isLibrarySessionFresh(
  snapshot: LibrarySessionSnapshot | null,
  query: LibraryQuery,
): boolean {
  if (!snapshot) return false;
  if (Date.now() - snapshot.savedAt > STALE_MS) return false;
  return queryKey(snapshot.query) === queryKey(query);
}

export function queriesMatchForList(a: LibraryQuery, b: LibraryQuery): boolean {
  return queryKey(a) === queryKey(b);
}

export function useLibrarySessionCache(
  query: LibraryQuery,
  items: LibraryItem[],
  total: number,
  scrollRoot: HTMLElement | null,
) {
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollTopRef = useRef(0);

  const persist = useCallback(
    (scrollTop?: number) => {
      if (typeof window === "undefined") return;
      try {
        const snapshot: LibrarySessionSnapshot = trimForStorage({
          query,
          items,
          total,
          scrollTop: scrollTop ?? scrollTopRef.current,
          savedAt: Date.now(),
        });
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
      } catch {
        /* quota exceeded — ignore */
      }
    },
    [query, items, total],
  );

  const schedulePersist = useCallback(() => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => persist(), 300);
  }, [persist]);

  useEffect(() => {
    schedulePersist();
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [schedulePersist]);

  useEffect(() => {
    if (!scrollRoot) return;

    const onScroll = () => {
      scrollTopRef.current = scrollRoot.scrollTop;
      if (scrollTimer.current) clearTimeout(scrollTimer.current);
      scrollTimer.current = setTimeout(() => persist(scrollRoot.scrollTop), 200);
    };

    scrollRoot.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scrollRoot.removeEventListener("scroll", onScroll);
      if (scrollTimer.current) clearTimeout(scrollTimer.current);
    };
  }, [scrollRoot, persist]);

  const clearSession = useCallback(() => {
    if (typeof window === "undefined") return;
    sessionStorage.removeItem(STORAGE_KEY);
  }, []);

  const restoreScroll = useCallback((scrollTop: number, root: HTMLElement | null) => {
    if (!root || scrollTop <= 0) return;
    requestAnimationFrame(() => {
      root.scrollTop = scrollTop;
    });
  }, []);

  return { clearSession, restoreScroll, persist };
}
