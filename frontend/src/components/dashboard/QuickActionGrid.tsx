import { Search, Mic2, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavigation, type View } from "@/contexts/NavigationContext";
import { GlowCard } from "@/components/ui/GlowCard";

const ACTIONS: {
  view: View;
  label: string;
  sub: string;
  icon: React.ElementType;
  accent: string;
  btn: string;
}[] = [
  {
    view: "harvest",
    label: "Harvest",
    sub: "Start Crawler",
    icon: Search,
    accent: "border-orange-500/20 shadow-glow-orange bg-orange-500/5",
    btn: "bg-orange-500/20 text-orange-300 hover:bg-orange-500/30",
  },
  {
    view: "processing",
    label: "Transcription",
    sub: "Run AI",
    icon: Mic2,
    accent: "border-violet-500/20 shadow-glow-purple bg-violet-500/5",
    btn: "bg-violet-500/20 text-violet-300 hover:bg-violet-500/30",
  },
  {
    view: "library",
    label: "Library",
    sub: "Sync Media",
    icon: BookOpen,
    accent: "border-blue-500/20 shadow-glow-blue bg-blue-500/5",
    btn: "bg-blue-500/20 text-blue-300 hover:bg-blue-500/30",
  },
];

export function QuickActionGrid() {
  const { navigateTo } = useNavigation();

  return (
    <GlowCard noPadding className="p-5 h-full min-h-[240px]">
      <p className="text-lg font-semibold text-slate-300 mb-4 px-1">Quick Actions</p>
      <div className="grid grid-cols-2 gap-3 h-[calc(100%-2.25rem)]">
        {ACTIONS.map(({ view, label, sub, icon: Icon, accent, btn }) => (
          <button
            key={view}
            type="button"
            onClick={() => navigateTo(view)}
            className={cn(
              "rounded-xl border p-4 text-left transition-all duration-200 h-full",
              "flex flex-col justify-between",
              "hover:-translate-y-0.5 gpu",
              accent,
            )}
          >
            <Icon className="w-6 h-6 mb-2 text-white/80" />
            <p className="text-xl font-semibold text-white">{label}</p>
            <span
              className={cn(
                "inline-block mt-2.5 text-base font-medium px-2.5 py-1.5 rounded-lg transition-colors",
                btn,
              )}
            >
              {sub}
            </span>
          </button>
        ))}
      </div>
    </GlowCard>
  );
}
