import { useState, useCallback, useRef, useEffect } from "react";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useAsync<T>(fn: () => Promise<T>, immediate = false) {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const mountedRef = useRef(true);

  const execute = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: null }));
    try {
      const data = await fn();
      if (mountedRef.current) setState({ data, loading: false, error: null });
    } catch (e) {
      if (mountedRef.current)
        setState(s => ({
          ...s,
          loading: false,
          error: e instanceof Error ? e.message : "오류 발생",
        }));
    }
  }, [fn]);

  const reset = useCallback(
    () => setState({ data: null, loading: false, error: null }),
    [],
  );

  useEffect(() => {
    mountedRef.current = true;
    if (immediate) execute();
    return () => { mountedRef.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, execute, reset };
}
