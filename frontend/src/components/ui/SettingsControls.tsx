import { useState } from "react";
import { ChevronDown, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";

function readSectionOpen(storageKey: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(storageKey);
    if (v === "0") return false;
    if (v === "1") return true;
  } catch {
    /* ignore */
  }
  return fallback;
}

export function SettingsSection({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
  storageKey,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  /** 접힘 상태 저장 키 (미지정 시 title 기반) */
  storageKey?: string;
}) {
  const persistKey = storageKey ?? `javstory.settings.section.${title}`;
  const [open, setOpen] = useState(() => readSectionOpen(persistKey, defaultOpen));

  const toggle = () => {
    setOpen(prev => {
      const next = !prev;
      try {
        localStorage.setItem(persistKey, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  return (
    <GlassCard noPadding className="overflow-hidden">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className={cn(
          "w-full flex items-center gap-2 px-5 py-4 text-left",
          "hover:bg-white/[0.025] transition-colors duration-150",
        )}
      >
        <div className="w-7 h-7 rounded-lg bg-accent/15 flex items-center justify-center shrink-0">
          <Icon className="w-3.5 h-3.5 text-accent-light" />
        </div>
        <h2 className="flex-1 text-lg font-semibold text-[#d0d0e8]">{title}</h2>
        <ChevronDown
          className={cn(
            "w-4 h-4 text-muted-foreground shrink-0",
            "transition-transform duration-250 ease-spring",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-300 ease-spring",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden min-h-0">
          <div className="px-5 pb-5 pt-1 space-y-4 border-t border-white/[0.06]">
            {children}
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

export function SettingsRow({
  label,
  hint,
  children,
  control = "default",
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  /** switch: 토글 등 컴팩트 컨트롤 — 오른쪽 정렬 */
  control?: "default" | "switch";
}) {
  const isSwitch = control === "switch";
  return (
    <div
      className={cn(
        "flex justify-between gap-4",
        isSwitch ? "items-center" : "items-start",
      )}
    >
      <div className={cn("min-w-0 flex-1", !isSwitch && "pt-1")}>
        <p className="text-base text-[#c8c8e0]">{label}</p>
        {hint && <p className="text-sm text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      <div className={cn(isSwitch ? "shrink-0" : "flex-1 max-w-xs w-full")}>
        {children}
      </div>
    </div>
  );
}

export function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full h-10 px-3 text-base rounded-xl bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all"
    />
  );
}

export function TextArea({ value, onChange, placeholder, rows = 6, className, readOnly }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  readOnly?: boolean;
}) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      readOnly={readOnly}
      className={cn(
        "w-full px-3 py-2 text-sm rounded-xl bg-bg-base border border-white/[0.08]",
        "text-white placeholder:text-muted-foreground font-mono leading-relaxed",
        "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all resize-y",
        readOnly && "focus:border-white/[0.08] focus:ring-0 cursor-default opacity-95",
        className,
      )}
    />
  );
}

export function SecretInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <TextInput value={value} onChange={onChange} placeholder={placeholder} type={visible ? "text" : "password"} />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-white transition-colors"
      >
        {visible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

export function SelectInput({ value, onChange, options }: {
  value: string;
  onChange: (v: string) => void;
  options: { label: string; value: string }[];
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full h-10 px-3 text-base rounded-xl bg-bg-base border border-white/[0.08] text-[#c8c8e0] focus:outline-none focus:border-accent/50 appearance-none"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  disabled = false,
  className,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex shrink-0 rounded-full transition-colors duration-200",
        "w-11 h-6",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-panel",
        checked ? "bg-accent" : "bg-white/[0.14]",
        disabled && "opacity-45 cursor-not-allowed",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm",
          "transition-[left] duration-200 ease-out",
          checked ? "left-[1.375rem]" : "left-0.5",
        )}
      />
    </button>
  );
}
