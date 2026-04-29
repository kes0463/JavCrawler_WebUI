import { useState } from "react";
import {
  LayoutDashboard, Search, Mic2, Layers,
  BookOpen, BarChart2, Settings, Bell,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavigation, type View } from "@/contexts/NavigationContext";

// 사이드바에 표시되는 모든 뷰 (설정 포함)
const NAV_ITEMS: { view: View; icon: React.ElementType; label: string }[] = [
  { view: "dashboard",  icon: LayoutDashboard, label: "대시보드" },
  { view: "harvest",    icon: Search,          label: "수집" },
  { view: "processing", icon: Mic2,            label: "전사·자막" },
  { view: "mosaic",     icon: Layers,          label: "모자이크" },
  { view: "library",    icon: BookOpen,        label: "라이브러리" },
  { view: "insight",    icon: BarChart2,       label: "인사이트" },
];

interface NavItemButtonProps {
  view: View;
  icon: React.ElementType;
  label: string;
  active: boolean;
  collapsed: boolean;
  onClick: () => void;
}

function NavItemButton({ view, icon: Icon, label, active, collapsed, onClick }: NavItemButtonProps) {
  return (
    <button
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        "relative w-full flex items-center gap-3 rounded-xl h-10",
        "transition-all duration-200 ease-spring gpu",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
        "focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel",
        collapsed ? "justify-center" : "px-3",
        active ? "nav-active-item" : "text-muted-foreground hover:bg-white/[0.04] hover:text-[#d0d0e8]",
      )}
    >
      <span
        className={cn(
          "absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full bg-accent",
          "transition-all duration-300 ease-spring",
          active ? "h-5 opacity-100 shadow-glow-sm" : "h-0 opacity-0",
        )}
      />
      <Icon className={cn(
        "shrink-0 transition-colors duration-200",
        collapsed ? "w-[18px] h-[18px]" : "w-4 h-4",
        active ? "text-accent-light" : "text-current",
      )} />
      {!collapsed && (
        <span className={cn("text-sm truncate", active ? "font-medium" : "font-normal")}>
          {label}
        </span>
      )}
    </button>
  );
}

interface NavSidebarProps {
  folderAlertCount?: number;
  onFolderAlertClick?: () => void;
}

export function NavSidebar({ folderAlertCount = 0, onFolderAlertClick }: NavSidebarProps) {
  const { currentView, navigateTo } = useNavigation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col h-full shrink-0 select-none",
        "border-r border-white/[0.06] bg-bg-panel",
        "shadow-[1px_0_0_rgba(255,255,255,0.03)]",
        "transition-[width] duration-300 ease-spring",
        collapsed ? "w-[64px]" : "w-[232px]",
      )}
    >
      {/* 로고 */}
      <div className="flex items-center h-[60px] px-3.5 border-b border-white/[0.06] shrink-0">
        <div className={cn(
          "rounded-xl flex items-center justify-center shrink-0",
          "bg-accent/20 border border-accent/25",
          "shadow-[0_0_16px_rgba(99,102,241,0.2),inset_0_1px_0_rgba(255,255,255,0.12)]",
          "transition-all duration-300",
          collapsed ? "w-8 h-8" : "w-7 h-7",
        )}>
          <span className="text-accent-light font-black text-[11px] tracking-tight">JS</span>
        </div>

        {!collapsed && (
          <span className="ml-2.5 text-sm font-extrabold tracking-[0.15em] text-gradient whitespace-nowrap overflow-hidden">
            JAVSTORY
          </span>
        )}

        <button
          onClick={() => setCollapsed(c => !c)}
          className={cn(
            "flex items-center justify-center rounded-lg w-6 h-6 shrink-0",
            "text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.05] transition-all duration-150",
            collapsed ? "mx-auto" : "ml-auto",
          )}
        >
          {collapsed
            ? <PanelLeftOpen className="w-3.5 h-3.5" />
            : <PanelLeftClose className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* 메인 네비게이션 */}
      <nav className="flex-1 overflow-y-auto no-scrollbar py-3 space-y-0.5 px-2">
        {NAV_ITEMS.map(({ view, icon, label }) => (
          <NavItemButton
            key={view}
            view={view}
            icon={icon}
            label={label}
            active={currentView === view}
            collapsed={collapsed}
            onClick={() => navigateTo(view)}
          />
        ))}
      </nav>

      {/* 하단 고정: 폴더 알림 + 설정 */}
      <div className="border-t border-white/[0.06] shrink-0 py-2.5 px-2 space-y-0.5">
        <button
          onClick={onFolderAlertClick}
          title={collapsed ? "폴더 알림" : undefined}
          className={cn(
            "relative w-full flex items-center gap-3 rounded-xl h-10",
            "text-muted-foreground hover:bg-white/[0.04] hover:text-[#d0d0e8]",
            "transition-all duration-200 ease-spring",
            collapsed ? "justify-center" : "px-3",
          )}
        >
          <div className="relative shrink-0">
            <Bell className="w-4 h-4" />
            {folderAlertCount > 0 && (
              <span className={cn(
                "absolute -top-1.5 -right-1.5 rounded-full",
                "bg-rose-500 text-white font-bold text-[9px]",
                "flex items-center justify-center h-4 min-w-[16px] px-1",
                "shadow-[0_0_8px_rgba(244,63,94,0.5)] animate-scale-in",
              )}>
                {folderAlertCount > 99 ? "99+" : folderAlertCount}
              </span>
            )}
          </div>
          {!collapsed && <span className="text-sm">폴더 알림</span>}
        </button>

        <NavItemButton
          view="settings"
          icon={Settings}
          label="설정"
          active={currentView === "settings"}
          collapsed={collapsed}
          onClick={() => navigateTo("settings")}
        />
      </div>
    </aside>
  );
}
