import { Search, Bell, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavigation, type View } from "@/contexts/NavigationContext";

const VIEW_TITLES: Record<View, string> = {
  dashboard: "Dashboard",
  harvest: "Harvest",
  processing: "Processing",
  mosaic: "Mosaic",
  library: "Library",
  actress: "배우",
  insight: "Insight",
  settings: "Settings",
};

interface AppHeaderProps {
  className?: string;
}

export function AppHeader({ className }: AppHeaderProps) {
  const { currentView } = useNavigation();
  const title = VIEW_TITLES[currentView];

  return (
    <header
      className={cn(
        "flex items-center gap-4 h-[60px] px-6 shrink-0",
        "border-b border-white/[0.06] bg-bg-panel/80 backdrop-blur-md",
        className,
      )}
    >
      <h1 className="text-3xl font-bold text-white tracking-tight shrink-0">{title}</h1>

      <div className="flex-1 max-w-lg mx-auto">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
          <input
            type="search"
            placeholder="Search library, codes, actors…"
            className={cn(
              "w-full h-10 pl-10 pr-4 rounded-xl text-base",
              "bg-white/[0.04] border border-white/[0.08]",
              "text-slate-200 placeholder:text-slate-500",
              "focus:outline-none focus:border-blue-500/40 focus:shadow-glow-blue",
              "transition-all duration-200",
            )}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          className="relative w-9 h-9 rounded-xl flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.05] transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]" />
        </button>
        <button
          type="button"
          className="flex items-center gap-2.5 h-10 px-3.5 rounded-xl text-base text-slate-300 hover:bg-white/[0.05] transition-colors"
        >
          <span className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs font-bold text-white">
            A
          </span>
          <span className="hidden sm:inline">Admin</span>
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        </button>
      </div>
    </header>
  );
}
