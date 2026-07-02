import { createContext, useContext, useState } from "react";
import { resolveActressByName } from "@/api/actress";

export type View =
  | "dashboard"
  | "harvest"
  | "processing"
  | "library"
  | "actress"
  | "insight"
  | "settings";

interface NavCtx {
  currentView: View;
  navigateTo: (view: View) => void;
  libraryDetailSku: string | null;
  openLibraryDetail: (sku: string) => void;
  closeLibraryDetail: () => void;
  actressDetailId: number | null;
  actressListEpoch: number;
  openActressDetail: (id: number) => void;
  openActressByName: (name: string) => Promise<boolean>;
  closeActressDetail: () => void;
  pendingActressCreateName: string | null;
  clearPendingActressCreate: () => void;
}

const NavigationContext = createContext<NavCtx | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [libraryDetailSku, setLibraryDetailSku] = useState<string | null>(null);
  const [actressDetailId, setActressDetailId] = useState<number | null>(null);
  const [actressListEpoch, setActressListEpoch] = useState(0);
  const [pendingActressCreateName, setPendingActressCreateName] = useState<string | null>(null);

  const navigateTo = (view: View) => {
    setCurrentView(view);
    if (view !== "library") setLibraryDetailSku(null);
    if (view !== "actress") setActressDetailId(null);
    if (view === "actress") {
      setActressDetailId(null);
      setActressListEpoch(e => e + 1);
    }
  };

  const openLibraryDetail = (sku: string) => {
    setCurrentView("library");
    setLibraryDetailSku(sku);
    setActressDetailId(null);
  };

  const openActressDetail = (id: number) => {
    setCurrentView("actress");
    setActressDetailId(id);
    setLibraryDetailSku(null);
  };

  const openActressByName = async (name: string): Promise<boolean> => {
    const trimmed = name.trim();
    if (!trimmed) return false;
    try {
      const res = await resolveActressByName(trimmed);
      setCurrentView("actress");
      setLibraryDetailSku(null);
      if (res.actress_id) {
        setActressDetailId(res.actress_id);
        setPendingActressCreateName(null);
        return true;
      }
      setActressDetailId(null);
      setPendingActressCreateName(trimmed);
      return false;
    } catch {
      setPendingActressCreateName(null);
      throw new Error("배우 정보를 불러오지 못했습니다.");
    }
  };

  return (
    <NavigationContext.Provider
      value={{
        currentView,
        navigateTo,
        libraryDetailSku,
        openLibraryDetail,
        closeLibraryDetail: () => setLibraryDetailSku(null),
        actressDetailId,
        actressListEpoch,
        openActressDetail,
        openActressByName,
        closeActressDetail: () => setActressDetailId(null),
        pendingActressCreateName,
        clearPendingActressCreate: () => setPendingActressCreateName(null),
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
