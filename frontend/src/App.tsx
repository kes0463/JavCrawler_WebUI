import { Suspense, lazy, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { NavigationProvider, useNavigation, type View } from "@/contexts/NavigationContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { FolderWatchProvider, useFolderWatch } from "@/contexts/FolderWatchContext";
import { PlayerProvider } from "@/contexts/PlayerContext";
import { NavSidebar } from "@/components/nav/NavSidebar";
import { AppHeader } from "@/components/layout/AppHeader";
import { GlowCard } from "@/components/ui/GlowCard";
import { AppScrollView } from "@/components/ui/AppScrollView";
import { useGlobalDragScroll } from "@/hooks/useGlobalDragScroll";

const DashboardView  = lazy(() => import("@/views/DashboardView"));
const HarvestView    = lazy(() => import("@/views/HarvestView"));
const ProcessingView = lazy(() => import("@/views/ProcessingView"));
const LibraryView    = lazy(() => import("@/views/LibraryView"));
const ActressView   = lazy(() => import("@/views/ActressView"));
const InsightView    = lazy(() => import("@/views/InsightView"));
const SettingsView   = lazy(() => import("@/views/SettingsView"));

const VIEW_MAP: { id: View; component: React.ComponentType }[] = [
  { id: "dashboard",  component: DashboardView },
  { id: "harvest",    component: HarvestView },
  { id: "processing", component: ProcessingView },
  { id: "library",    component: LibraryView },
  { id: "actress",    component: ActressView },
  { id: "insight",    component: InsightView },
  { id: "settings",   component: SettingsView },
];

/** 탭 전환 시 언마운트하지 않고 목록·스크롤 상태를 유지할 화면 */
const PERSIST_VIEWS: ReadonlySet<View> = new Set(["actress", "library"]);

function ViewStack() {
  const { currentView } = useNavigation();
  const [visited, setVisited] = useState<Set<View>>(() => new Set([currentView]));

  useEffect(() => {
    setVisited(prev => {
      if (prev.has(currentView)) return prev;
      const next = new Set(prev);
      next.add(currentView);
      return next;
    });
  }, [currentView]);

  return (
    <div className="flex-1 min-w-0 relative min-h-0">
      {VIEW_MAP.map(({ id, component: ViewComp }) => {
        const keepMounted = PERSIST_VIEWS.has(id) && visited.has(id);
        if (currentView !== id && !keepMounted) return null;
        const active = currentView === id;
        return (
          <AppScrollView
            key={id}
            className={cn(
              "absolute inset-0 view-layer-enter",
              active ? "view-layer-active z-10" : "view-layer-hidden invisible z-0",
            )}
            aria-hidden={!active}
            data-drag-scroll-root={active ? undefined : "off"}
          >
            <div className="px-6 py-5 w-full min-w-0">
              <Suspense fallback={<PageSkeleton />}>
                <ViewComp />
              </Suspense>
            </div>
          </AppScrollView>
        );
      })}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4 animate-pulse w-full">
      <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-4 w-full">
        {[0, 1, 2].map(i => (
          <GlowCard key={i}>
            <div className="h-24 rounded-lg bg-bg-surface" />
          </GlowCard>
        ))}
      </div>
    </div>
  );
}

function AppShell() {
  useGlobalDragScroll();
  const { alertCount, openInbox } = useFolderWatch();

  return (
    <div className="flex h-screen bg-bg-base text-[#e2e2f0] overflow-hidden">
      <NavSidebar folderAlertCount={alertCount} onFolderAlertClick={openInbox} />
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader folderAlertCount={alertCount} onFolderAlertClick={openInbox} />
        <ViewStack />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <NavigationProvider>
      <ToastProvider>
        <FolderWatchProvider>
          <PlayerProvider>
            <AppShell />
          </PlayerProvider>
        </FolderWatchProvider>
      </ToastProvider>
    </NavigationProvider>
  );
}
