import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { ToastNotification } from "@/components/ui/ToastNotification";

export type ToastLevel = "info" | "success" | "warn" | "error";

interface ToastItem {
  id: number;
  message: string;
  level: ToastLevel;
}

interface ToastCtx {
  showToast: (message: string, level?: ToastLevel) => void;
}

const ToastContext = createContext<ToastCtx | null>(null);
let _nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  // 언마운트 시 잔여 타이머 전체 해제
  useEffect(() => {
    const timers = timersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  const dismiss = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts(t => t.filter(x => x.id !== id));
  }, []);

  const showToast = useCallback((message: string, level: ToastLevel = "info") => {
    const id = ++_nextId;
    setToasts(t => [...t, { id, message, level }]);
    const timer = setTimeout(() => dismiss(id), 3500);
    timersRef.current.set(id, timer);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[200] flex flex-col gap-2 items-center pointer-events-none">
        {toasts.map(t => (
          <ToastNotification
            key={t.id}
            message={t.message}
            level={t.level}
            onDismiss={() => dismiss(t.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
