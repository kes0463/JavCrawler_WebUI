import { useState, useCallback, useMemo } from "react";

export function useSelection<T>(items: T[], getKey: (item: T) => string) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const isSelected = useCallback(
    (item: T) => selected.has(getKey(item)),
    [selected, getKey],
  );

  const isSelectedKey = useCallback(
    (key: string) => selected.has(key),
    [selected],
  );

  const toggle = useCallback(
    (item: T) => {
      const key = getKey(item);
      setSelected(prev => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
    },
    [getKey],
  );

  const select = useCallback(
    (item: T) => {
      const key = getKey(item);
      setSelected(prev => {
        if (prev.has(key)) return prev;
        const next = new Set(prev);
        next.add(key);
        return next;
      });
    },
    [getKey],
  );

  const selectKey = useCallback((key: string) => {
    setSelected(prev => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }, []);

  const selectAll = useCallback(
    () => setSelected(new Set(items.map(getKey))),
    [items, getKey],
  );

  const clearAll = useCallback(() => setSelected(new Set()), []);

  const allSelected = useMemo(
    () => items.length > 0 && items.every(item => selected.has(getKey(item))),
    [items, selected, getKey],
  );

  const selectedKeys = useMemo(() => Array.from(selected), [selected]);

  return {
    selected,
    selectedKeys,
    isSelected,
    isSelectedKey,
    toggle,
    select,
    selectKey,
    selectAll,
    clearAll,
    count: selected.size,
    allSelected,
  };
}
