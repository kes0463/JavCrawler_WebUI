import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge, type StatusType } from "@/components/ui/StatusBadge";

interface QueueAccordionCardProps {
  title: string;
  icon?: string;
  count?: number;
  status?: StatusType;
  defaultOpen?: boolean;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function QueueAccordionCard({
  title,
  icon,
  count,
  status,
  defaultOpen = true,
  actions,
  children,
  className,
}: QueueAccordionCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <GlassCard noPadding className={cn("overflow-hidden", className)}>
      <button
        onClick={() => setOpen(o => !o)}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-4 text-left",
          "hover:bg-white/[0.025] transition-colors duration-150",
        )}
      >
        {icon && <span className="text-[15px] leading-none">{icon}</span>}

        <span className="flex-1 text-lg font-semibold text-[#d4d4ec] tracking-tight">{title}</span>

        {count !== undefined && (
          <span className="text-sm tabular-nums text-zinc-500 px-2.5 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.06]">
            {count}
          </span>
        )}

        {status && <StatusBadge status={status} />}

        {actions && (
          <div onClick={e => e.stopPropagation()} className="flex items-center gap-1.5">
            {actions}
          </div>
        )}

        <ChevronDown
          className={cn(
            "w-3.5 h-3.5 text-zinc-600 shrink-0",
            "transition-transform duration-250 ease-spring",
            open && "rotate-180",
          )}
        />
      </button>

      <div
        className={cn(
          "overflow-hidden",
          "transition-all duration-300 ease-spring",
          open ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <div className="px-4 pb-4 pt-3 space-y-2 border-t border-white/[0.05]">
          {children}
        </div>
      </div>
    </GlassCard>
  );
}
