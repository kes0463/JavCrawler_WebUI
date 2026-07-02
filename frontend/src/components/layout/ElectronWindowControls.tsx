import { useEffect, useState } from "react";
import { Minus, Square, X, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { isElectron } from "@/lib/folderPaths";

export function ElectronWindowControls({ className }: { className?: string }) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    const controls = window.javstory?.windowControls;
    if (!controls) return;

    void controls.isMaximized().then(setMaximized);
    return controls.onMaximizedChange(setMaximized);
  }, []);

  if (!isElectron() || !window.javstory?.windowControls) return null;

  const { minimize, maximize, close } = window.javstory.windowControls;

  return (
    <div className={cn("flex items-center h-full electron-no-drag", className)}>
      <button
        type="button"
        onClick={() => void minimize()}
        className="w-11 h-[60px] flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
        aria-label="최소화"
      >
        <Minus className="w-4 h-4" strokeWidth={1.75} />
      </button>
      <button
        type="button"
        onClick={() => void maximize().then(setMaximized)}
        className="w-11 h-[60px] flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
        aria-label={maximized ? "이전 크기로 복원" : "최대화"}
      >
        {maximized
          ? <Copy className="w-3.5 h-3.5" strokeWidth={1.75} />
          : <Square className="w-3.5 h-3.5" strokeWidth={1.75} />}
      </button>
      <button
        type="button"
        onClick={() => void close()}
        className="w-11 h-[60px] flex items-center justify-center text-slate-400 hover:text-white hover:bg-rose-600 transition-colors"
        aria-label="닫기"
      >
        <X className="w-4 h-4" strokeWidth={1.75} />
      </button>
    </div>
  );
}
