import { useState, useCallback, useMemo } from "react";

export function useSelection<T>(items: T[], getKey: (item: T) => string) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const isSelected = useCallback(
    (item: T) => selected.has(getKey(item)),
    [selected, getKey],
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

  const selectAll = useCallback(
    () => setSelected(new Set(items.map(getKey))),
    [items, getKey],
  );

  const clearAll = useCallback(() => setSelected(new Set()), []);

  const allSelected = useMemo(
    () => items.length > 0 && items.every(item => selected.has(getKey(item))),
    [items, selected, getKey],
  );

  return {
    selected,
    isSelected,
    toggle,
    selectAll,
    clearAll,
    count: selected.size,
    allSelected,
  };
}
