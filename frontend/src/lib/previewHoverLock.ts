type Listener = (activeId: string | null) => void;

let activeId: string | null = null;
const listeners = new Set<Listener>();

export function subscribePreviewHover(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function claimPreviewHover(id: string): void {
  activeId = id;
  listeners.forEach(fn => fn(activeId));
}

export function releasePreviewHover(id: string): void {
  if (activeId !== id) return;
  activeId = null;
  listeners.forEach(fn => fn(activeId));
}

export function getActivePreviewHover(): string | null {
  return activeId;
}
