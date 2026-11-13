import { createContext, useContext, useState } from "react";
import { resolveActressByName } from "@/api/actress";

export type View =
  | "dashboard"
  | "harvest"
  | "processing"
  | "library"
  | "actress"
  | "insight"
  | "personaChat"
  | "settings";

/** 다른 화면에서 Persona Chat으로 딥링크할 때 넘기는 진입 컨텍스트 — 소비 후 즉시 비운다. */
export interface PersonaChatEntryContext {
  /** 채팅 상세 패널을 이 작품으로 열고, 다음 메시지의 product_code 컨텍스트로 붙인다. */
  productCode?: string;
  /** 입력창에 미리 채워 둘 메시지 — 사용자가 확인 후 전송한다. */
  prefillMessage?: string;
}

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
  personaChatEntry: PersonaChatEntryContext | null;
  openPersonaChat: (ctx?: PersonaChatEntryContext) => void;
  clearPersonaChatEntry: () => void;
}

const NavigationContext = createContext<NavCtx | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [libraryDetailSku, setLibraryDetailSku] = useState<string | null>(null);
  const [actressDetailId, setActressDetailId] = useState<number | null>(null);
  const [actressListEpoch, setActressListEpoch] = useState(0);
  const [pendingActressCreateName, setPendingActressCreateName] = useState<string | null>(null);
  const [personaChatEntry, setPersonaChatEntry] = useState<PersonaChatEntryContext | null>(null);

  /** 라이브러리 상세를 유지할 탭 — STT/번역 후 복귀 시 패널 복원 */
  const PRESERVE_LIBRARY_DETAIL: View[] = ["processing"];

  const navigateTo = (view: View) => {
    setCurrentView(view);
    if (view !== "library" && !PRESERVE_LIBRARY_DETAIL.includes(view)) {
      setLibraryDetailSku(null);
    }
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

  /** 라이브러리/배우 상세 등에서 특정 작품·배우를 문맥으로 Persona Chat 탭을 연다. */
  const openPersonaChat = (ctx?: PersonaChatEntryContext) => {
    setCurrentView("personaChat");
    setLibraryDetailSku(null);
    setActressDetailId(null);
    setPersonaChatEntry(ctx ?? {});
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
        personaChatEntry,
        openPersonaChat,
        clearPersonaChatEntry: () => setPersonaChatEntry(null),
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
