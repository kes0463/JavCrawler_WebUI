import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";

export function SettingsSection({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <GlassCard className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-white/[0.06]">
        <div className="w-7 h-7 rounded-lg bg-accent/15 flex items-center justify-center">
          <Icon className="w-3.5 h-3.5 text-accent-light" />
        </div>
        <h2 className="text-sm font-semibold text-[#d0d0e8]">{title}</h2>
      </div>
      <div className="space-y-4">{children}</div>
    </GlassCard>
  );
}

export function SettingsRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="shrink-0 pt-1">
        <p className="text-sm text-[#c8c8e0]">{label}</p>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      <div className="flex-1 max-w-xs">{children}</div>
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
      className="w-full h-9 px-3 text-sm rounded-xl bg-bg-base border border-white/[0.08] text-white placeholder:text-muted-foreground focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all"
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
      className="w-full h-9 px-3 text-sm rounded-xl bg-bg-base border border-white/[0.08] text-[#c8c8e0] focus:outline-none focus:border-accent/50 appearance-none"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative w-10 h-5 rounded-full transition-colors duration-200 ${checked ? "bg-accent" : "bg-white/[0.12]"}`}
    >
      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${checked ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}
