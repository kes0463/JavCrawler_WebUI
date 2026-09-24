import { Loader2 } from "lucide-react";
import { AppSelect, LIBRARY_SELECT_TRIGGER_CLASS } from "@/components/ui/AppSelect";
import type { UseLlamaCppModelPicker } from "@/hooks/useLlamaCppModelPicker";
import { cn } from "@/lib/utils";

interface ModelPickerDropdownProps {
  picker: UseLlamaCppModelPicker;
  className?: string;
}

/** Insight·Persona Chat이 공유하는 llama.cpp 모델 선택 드롭다운 + 로딩 상태 pill. */
export function ModelPickerDropdown({ picker, className }: ModelPickerDropdownProps) {
  const { options, selectedId, status, personaChatManaged, onSelect } = picker;

  if (!personaChatManaged) {
    return (
      <span className="text-xs text-slate-500">
        외부 llama.cpp 서버 사용 중 — 모델 선택 비활성
      </span>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <AppSelect
        value={selectedId}
        onChange={onSelect}
        options={options.map(o => ({ value: o.id, label: o.label }))}
        triggerClassName={cn(LIBRARY_SELECT_TRIGGER_CLASS, "h-9 text-sm min-w-[10rem]")}
        aria-label="llama.cpp 모델 선택"
      />
      {status === "spawning" && (
        <span className="inline-flex items-center gap-1.5 text-xs text-indigo-300">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          로딩 중…
        </span>
      )}
      {status === "busy" && (
        <span className="inline-flex items-center gap-1.5 text-xs text-emerald-300">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          사용 중
        </span>
      )}
    </div>
  );
}
