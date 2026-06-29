import { useState } from "react";
import {
  LayoutDashboard, Search, Mic2, Layers,
  BookOpen, BarChart2, Settings, Bell, Users,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useNavigation, type View } from "@/contexts/NavigationContext";

// 사이드바에 표시되는 모든 뷰 (설정 포함)
const NAV_ITEMS: { view: View; icon: React.ElementType; label: string; badge?: string }[] = [
  { view: "dashboard",  icon: LayoutDashboard, label: "Dashboard" },
  { view: "library",    icon: BookOpen,        label: "Library" },
  { view: "actress",    icon: Users,           label: "Actresses" },
  { view: "mosaic",     icon: Layers,          label: "Mosaic", badge: "Soon" },
  { view: "harvest",    icon: Search,          label: "Queues" },
  { view: "processing", icon: Mic2,            label: "Tasks", badge: "Soon" },
  { view: "insight",    icon: BarChart2,       label: "System", badge: "Soon" },
];

interface NavItemButtonProps {
  view: View;
  icon: React.ElementType;
  label: string;
  badge?: string;
  active: boolean;
  collapsed: boolean;
  onClick: () => void;
}

function NavItemButton({ view, icon: Icon, label, badge, active, collapsed, onClick }: NavItemButtonProps) {
  return (
    <button
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        "relative w-full flex items-center gap-4 rounded-xl h-12",
        "transition-all duration-200 ease-spring gpu",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
        "focus-visible:ring-offset-1 focus-visible:ring-offset-bg-panel",
        collapsed ? "justify-center" : "px-4",
        active ? "nav-active-item shadow-glow-blue" : "text-muted-foreground hover:bg-white/[0.04] hover:text-[#d0d0e8]",
      )}
    >
      <span
        className={cn(
          "absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full bg-accent",
          "transition-all duration-300 ease-spring",
          active ? "h-6 opacity-100 shadow-glow-sm" : "h-0 opacity-0",
        )}
      />
      <Icon className={cn(
        "shrink-0 transition-colors duration-200 w-6 h-6",
        active ? "text-accent-light" : "text-current",
      )} />
      {!collapsed && (
        <span className={cn("text-lg truncate flex items-center gap-2", active ? "font-semibold" : "font-medium")}>
          {label}
          {badge && (
            <span className="text-sm px-2 py-0.5 rounded-md bg-white/[0.06] text-slate-500 font-medium">
              {badge}
            </span>
          )}
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
        collapsed ? "w-[80px]" : "w-[288px]",
      )}
    >
      {/* 로고 */}
      <div className="flex items-center h-[72px] px-4 border-b border-white/[0.06] shrink-0">
        <div className={cn(
          "rounded-xl flex items-center justify-center shrink-0",
          "bg-accent/20 border border-accent/25",
          "shadow-[0_0_16px_rgba(99,102,241,0.2),inset_0_1px_0_rgba(255,255,255,0.12)]",
          "transition-all duration-300",
          collapsed ? "w-10 h-10" : "w-9 h-9",
        )}>
          <span className="text-accent-light font-black text-sm tracking-tight">JS</span>
        </div>

        {!collapsed && (
          <span className="ml-3 text-lg font-extrabold tracking-[0.1em] text-gradient whitespace-nowrap overflow-hidden">
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
      <nav className="flex-1 overflow-y-auto app-scroll no-scrollbar py-4 space-y-1.5 px-3">
        {NAV_ITEMS.map(({ view, icon, label, badge }) => (
          <NavItemButton
            key={view}
            view={view}
            icon={icon}
            label={label}
            badge={badge}
            active={currentView === view}
            collapsed={collapsed}
            onClick={() => navigateTo(view)}
          />
        ))}
      </nav>

      {/* 하단 고정: 폴더 알림 + 설정 */}
      <div className="border-t border-white/[0.06] shrink-0 py-3 px-2.5 space-y-1">
        <button
          onClick={onFolderAlertClick}
          title={collapsed ? "폴더 알림" : undefined}
          className={cn(
            "relative w-full flex items-center gap-4 rounded-xl h-12",
            "text-muted-foreground hover:bg-white/[0.04] hover:text-[#d0d0e8]",
            "transition-all duration-200 ease-spring",
            collapsed ? "justify-center" : "px-4",
          )}
        >
          <div className="relative shrink-0">
            <Bell className="w-6 h-6" />
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
          {!collapsed && <span className="text-lg font-medium">폴더 알림</span>}
        </button>

        <NavItemButton
          view="settings"
          icon={Settings}
          label="Settings"
          active={currentView === "settings"}
          collapsed={collapsed}
          onClick={() => navigateTo("settings")}
        />

        {!collapsed && (
          <div className="flex items-center gap-3.5 px-4 py-3 mt-1 rounded-xl text-slate-400">
            <span className="w-9 h-9 rounded-full bg-gradient-to-br from-slate-600 to-slate-800 flex items-center justify-center text-sm font-bold text-white shrink-0">
              U
            </span>
            <span className="text-lg font-medium truncate">User Profile</span>
          </div>
        )}
      </div>
    </aside>
  );
}
