import { cn } from "@/lib/utils";

export type InsightTabId = "overview" | "trends" | "recommend" | "collection";

const TABS: { id: InsightTabId; label: string }[] = [
  { id: "overview", label: "개요" },
  { id: "trends", label: "트렌드" },
  { id: "recommend", label: "추천" },
  { id: "collection", label: "컬렉션" },
];

interface InsightTabBarProps {
  active: InsightTabId;
  onChange: (tab: InsightTabId) => void;
}

export function InsightTabBar({ active, onChange }: InsightTabBarProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          className={cn(
            "px-4 py-2 rounded-xl text-sm font-medium border transition-colors",
            active === id
              ? "bg-accent/20 border-accent/40 text-accent-light"
              : "border-white/10 text-slate-400 hover:bg-white/[0.04] hover:text-slate-200",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
