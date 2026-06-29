import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { fetchPlaybackInfo } from "@/api/playback";
import type { PlaybackInfo } from "@/api/playback";
import { VideoPlayer } from "@/components/player/VideoPlayer";

/** LibraryDetailPanel(z-110)보다 위 — body 포털 필수 */
const PLAYER_LAYER_Z = 120;

interface PlayerContextValue {
  openPlayer: (productCode: string) => Promise<void>;
  closePlayer: () => void;
  isOpen: boolean;
}

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<PlaybackInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const closePlayer = useCallback(() => {
    setSession(null);
    setError(null);
  }, []);

  const openPlayer = useCallback(async (productCode: string) => {
    const code = productCode.trim().toUpperCase();
    if (!code) return;
    setLoading(true);
    setError(null);
    try {
      const info = await fetchPlaybackInfo(code);
      setSession(info);
    } catch (e) {
      setError(e instanceof Error ? e.message : "재생 정보를 불러오지 못했습니다");
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      openPlayer,
      closePlayer,
      isOpen: !!session,
    }),
    [openPlayer, closePlayer, session],
  );

  const playerOverlay =
    loading || error || session
      ? (
        <>
          {loading && (
            <div
              className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm"
              style={{ zIndex: PLAYER_LAYER_Z }}
            >
              <p className="text-white text-sm">재생 준비 중…</p>
            </div>
          )}
          {error && !session && (
            <div
              className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6"
              style={{ zIndex: PLAYER_LAYER_Z }}
            >
              <div className="max-w-md rounded-xl border border-rose-500/30 bg-bg-card p-5 text-center space-y-3">
                <p className="text-rose-300 text-sm">{error}</p>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-sm text-white"
                >
                  닫기
                </button>
              </div>
            </div>
          )}
          {session && <VideoPlayer session={session} onClose={closePlayer} />}
        </>
      )
      : null;

  return (
    <PlayerContext.Provider value={value}>
      {children}
      {typeof document !== "undefined" && playerOverlay
        ? createPortal(playerOverlay, document.body)
        : null}
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
