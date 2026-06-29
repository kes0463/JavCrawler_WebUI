import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AppSelectOption<T extends string | number = string | number> {
  value: T;
  label: string;
}

export const LIBRARY_SELECT_TRIGGER_CLASS =
  "h-10 pl-3 pr-9 text-base rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-colors";

interface AppSelectProps<T extends string | number> {
  value: T;
  onChange: (value: T) => void;
  options: AppSelectOption<T>[];
  className?: string;
  triggerClassName?: string;
  menuClassName?: string;
  placement?: "top" | "bottom";
  disabled?: boolean;
  "aria-label"?: string;
}

export function AppSelect<T extends string | number>({
  value,
  onChange,
  options,
  className,
  triggerClassName,
  menuClassName,
  placement = "bottom",
  disabled = false,
  "aria-label": ariaLabel,
}: AppSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selected = options.find(o => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative min-w-0", className)}>
      <button
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className={cn(
          LIBRARY_SELECT_TRIGGER_CLASS,
          "relative w-full text-left truncate disabled:opacity-50 disabled:pointer-events-none",
          triggerClassName,
        )}
        onClick={e => {
          e.stopPropagation();
          setOpen(o => !o);
        }}
      >
        <span className="block truncate">{selected?.label ?? "—"}</span>
        <ChevronDown
          className={cn(
            "pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <ul
          id={listId}
          role="listbox"
          className={cn(
            "absolute z-[120] min-w-full w-max max-w-[min(28rem,calc(100vw-2rem))] max-h-60 overflow-y-auto rounded-xl py-1",
            "bg-bg-surface border border-white/[0.08] shadow-float",
            placement === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
            menuClassName,
          )}
          onClick={e => e.stopPropagation()}
        >
          {options.map(opt => {
            const active = opt.value === value;
            return (
              <li key={String(opt.value)} role="option" aria-selected={active}>
                <button
                  type="button"
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm truncate transition-colors",
                    active
                      ? "bg-indigo-500/20 text-indigo-200"
                      : "text-[#c8c8e0] hover:bg-white/[0.06] hover:text-white",
                  )}
                  onClick={e => {
                    e.stopPropagation();
                    onChange(opt.value);
                    setOpen(false);
                  }}
                >
                  {opt.label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
