import { Suspense, lazy, useState, useEffect } from "react";
import { NavigationProvider, useNavigation, type View } from "@/contexts/NavigationContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { NavSidebar } from "@/components/nav/NavSidebar";
import { GlassCard } from "@/components/ui/GlassCard";
import { AppScrollView } from "@/components/ui/AppScrollView";

const DashboardView  = lazy(() => import("@/views/DashboardView"));
const HarvestView    = lazy(() => import("@/views/HarvestView"));
const ProcessingView = lazy(() => import("@/views/ProcessingView"));
const MosaicView     = lazy(() => import("@/views/MosaicImportView"));
const LibraryView    = lazy(() => import("@/views/LibraryView"));
const InsightView    = lazy(() => import("@/views/InsightView"));
const SettingsView   = lazy(() => import("@/views/SettingsView"));

const VIEW_MAP: { id: View; component: React.ComponentType }[] = [
  { id: "dashboard",  component: DashboardView },
  { id: "harvest",    component: HarvestView },
  { id: "processing", component: ProcessingView },
  { id: "mosaic",     component: MosaicView },
  { id: "library",    component: LibraryView },
  { id: "insight",    component: InsightView },
  { id: "settings",   component: SettingsView },
];

function ViewStack() {
  const { currentView } = useNavigation();
  // 한 번 방문한 뷰는 언마운트하지 않고 hidden으로 숨김 (상태 보존)
  const [mounted, setMounted] = useState<Set<View>>(() => new Set([currentView]));

  useEffect(() => {
    setMounted(prev => {
      if (prev.has(currentView)) return prev;
      const next = new Set(prev);
      next.add(currentView);
      return next;
    });
  }, [currentView]);

  return (
    <AppScrollView className="flex-1 min-w-0">
      {VIEW_MAP.map(({ id, component: View }) => (
        <div key={id} hidden={currentView !== id} className="px-6 py-6">
          {mounted.has(id) && (
            <Suspense fallback={<PageSkeleton />}>
              <View />
            </Suspense>
          )}
        </div>
      ))}
    </AppScrollView>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-7 w-40 rounded-xl bg-bg-surface" />
      <div className="h-4 w-64 rounded-lg bg-bg-surface" />
      <div className="grid grid-cols-4 gap-3 mt-6">
        {[0, 1, 2, 3].map(i => (
          <GlassCard key={i}>
            <div className="h-4 w-20 rounded-lg bg-bg-surface mb-3" />
            <div className="h-7 w-16 rounded-lg bg-bg-hover" />
          </GlassCard>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map(i => (
          <GlassCard key={i} className="h-40">
            <div className="h-full rounded-lg bg-bg-surface" />
          </GlassCard>
        ))}
      </div>
    </div>
  );
}

function AppShell() {
  return (
    <div className="flex h-screen bg-bg-base text-[#e2e2f0] overflow-hidden">
      <NavSidebar />
      <ViewStack />
    </div>
  );
}

export default function App() {
  return (
    <NavigationProvider>
      <ToastProvider>
        <AppShell />
      </ToastProvider>
    </NavigationProvider>
  );
}
