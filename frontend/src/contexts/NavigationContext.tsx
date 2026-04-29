import { createContext, useContext, useState } from "react";

export type View =
  | "dashboard"
  | "harvest"
  | "processing"
  | "mosaic"
  | "library"
  | "insight"
  | "settings";

interface NavCtx {
  currentView: View;
  navigateTo: (view: View) => void;
  libraryDetailSku: string | null;
  openLibraryDetail: (sku: string) => void;
  closeLibraryDetail: () => void;
}

const NavigationContext = createContext<NavCtx | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [libraryDetailSku, setLibraryDetailSku] = useState<string | null>(null);

  const navigateTo = (view: View) => {
    setCurrentView(view);
    if (view !== "library") setLibraryDetailSku(null);
  };

  const openLibraryDetail = (sku: string) => {
    setCurrentView("library");
    setLibraryDetailSku(sku);
  };

  return (
    <NavigationContext.Provider
      value={{
        currentView,
        navigateTo,
        libraryDetailSku,
        openLibraryDetail,
        closeLibraryDetail: () => setLibraryDetailSku(null),
      }}
    >
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation() {
  const ctx = useContext(NavigationContext);
  if (!ctx) throw new Error("useNavigation must be used within NavigationProvider");
  return ctx;
}
