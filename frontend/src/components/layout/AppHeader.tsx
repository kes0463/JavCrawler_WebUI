import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";
import { isElectron } from "@/lib/folderPaths";
import { useNavigation, type View } from "@/contexts/NavigationContext";
import { ElectronWindowControls } from "@/components/layout/ElectronWindowControls";

const VIEW_TITLES: Record<View, string> = {
  dashboard: "Dashboard",
  harvest: "Harvest",
  processing: "전사 · 자막",
  library: "Library",
  actress: "배우",
  insight: "Insight",
  settings: "Settings",
};

interface AppHeaderProps {
  className?: string;
  folderAlertCount?: number;
  onFolderAlertClick?: () => void;
}

export function AppHeader({ className, folderAlertCount = 0, onFolderAlertClick }: AppHeaderProps) {
  const { currentView } = useNavigation();
  const title = VIEW_TITLES[currentView];

  const electron = isElectron();

  return (
    <header
      className={cn(
        "flex items-center gap-4 h-[60px] shrink-0",
        "border-b border-white/[0.06] bg-bg-panel/80 backdrop-blur-md",
        electron ? "pl-6 pr-0 electron-drag" : "px-6",
        className,
      )}
    >
      <h1 className="text-3xl font-bold text-white tracking-tight shrink-0 select-none">{title}</h1>

      <div className="flex-1" />

      <div className="flex items-center gap-2 shrink-0 electron-no-drag">
        <button
          type="button"
          onClick={onFolderAlertClick}
          className="relative w-9 h-9 rounded-xl flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.05] transition-colors"
          aria-label="폴더 알림"
        >
          <Bell className="w-4 h-4" />
          {folderAlertCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center shadow-[0_0_8px_rgba(244,63,94,0.8)]">
              {folderAlertCount > 99 ? "99+" : folderAlertCount}
            </span>
          )}
        </button>
        <ElectronWindowControls />
      </div>
    </header>
  );
}
