import { useEffect } from "react";

const DRAG_THRESHOLD_PX = 8;
const CLICK_SUPPRESS_PX = 14;
const VELOCITY_SMOOTHING = 0.62;
const VELOCITY_SCALE = 12;
const MAX_SPEED_MULTIPLIER = 2.4;
const MOMENTUM_GAIN = 1.0;
const MOMENTUM_FRICTION = 0.91;
const MOMENTUM_MIN_VELOCITY = 0.012;
const NEAR_END_PX = 200;
const INFINITE_SCROLL_NEAR_END = "infinite-scroll-near-end";
const IGNORE_SELECTOR =
  "button, a, input, textarea, select, option, summary, [contenteditable], [data-no-drag-scroll], [data-poster-card], [role='button'], [role='separator']";
const TEXT_ANCESTOR_SELECTOR =
  "p, span, h1, h2, h3, h4, h5, h6, li, td, th, pre, code, em, strong, small, blockquote, figcaption, dt, dd, time, [data-selectable-text]";

interface DragState {
  scrollEl: HTMLElement;
  startY: number;
  lastY: number;
  lastTime: number;
  velocity: number;
  active: boolean;
  moved: boolean;
  totalDelta: number;
}

let dragState: DragState | null = null;
let suppressClick = false;
let momentumRaf = 0;
let momentumEl: HTMLElement | null = null;
let momentumVelocity = 0;
let momentumLastTime = 0;
let momentumResizeObserver: ResizeObserver | null = null;
let nearEndLastFire = 0;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function resolveElement(target: EventTarget | null): HTMLElement | null {
  if (!target) return null;
  if (target instanceof Text) return target.parentElement;
  if (target instanceof HTMLElement) return target;
  return null;
}

function isVerticallyScrollable(el: HTMLElement): boolean {
  const { overflowY } = getComputedStyle(el);
  if (overflowY !== "auto" && overflowY !== "scroll" && overflowY !== "overlay") return false;
  return el.scrollHeight > el.clientHeight + 1;
}

export function getScrollableAncestor(start: HTMLElement | null): HTMLElement | null {
  let el = start;
  while (el && el !== document.documentElement) {
    if (el.hasAttribute("data-drag-scroll-root") && el.getAttribute("data-drag-scroll-root") === "off") {
      return null;
    }
    if (isVerticallyScrollable(el)) return el;
    el = el.parentElement;
  }
  return null;
}

function findScrollableAncestor(start: HTMLElement | null): HTMLElement | null {
  return getScrollableAncestor(start);
}

function nearEndThresholdPx(el: HTMLElement): number {
  const raw = el.dataset.infiniteNearEndPx;
  if (!raw) return NEAR_END_PX;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : NEAR_END_PX;
}

function dispatchNearEnd(el: HTMLElement) {
  const now = performance.now();
  if (now - nearEndLastFire < 40) return;
  nearEndLastFire = now;
  el.dispatchEvent(new CustomEvent(INFINITE_SCROLL_NEAR_END, { bubbles: true }));
}

function hasMoreInfiniteContent(el: HTMLElement): boolean {
  return el.dataset.infiniteScroll === "active";
}

function maybeDispatchNearEnd(el: HTMLElement, velocity: number) {
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
  const distFromBottom = maxScroll - el.scrollTop;
  const nearEnd = nearEndThresholdPx(el);
  // velocity < 0: 위로 스와이프 → 아래 콘텐츠 방향
  if (velocity < 0 && distFromBottom < nearEnd) {
    dispatchNearEnd(el);
  }
}

function isTextSelectionTarget(target: EventTarget | null): boolean {
  const el = resolveElement(target);
  if (!el) return false;
  if (el.closest("img, svg, video, canvas, picture")) return false;

  const textHost = el.closest(TEXT_ANCESTOR_SELECTOR);
  if (!textHost) return false;
  if (getComputedStyle(textHost).userSelect === "none") return false;

  return (textHost.textContent?.trim().length ?? 0) > 0;
}

function shouldIgnoreTarget(target: EventTarget | null): boolean {
  const el = resolveElement(target);
  if (!el) return true;
  if (el.closest(IGNORE_SELECTOR)) return true;
  if (el.hasAttribute("data-modal-overlay") || el.hasAttribute("data-lightbox")) return true;
  return false;
}

function clearDragStyle(el: HTMLElement | null) {
  if (!el) return;
  el.style.cursor = "";
  el.style.userSelect = "";
}

function speedMultiplier(velocityPxPerMs: number): number {
  const speed = Math.abs(velocityPxPerMs);
  return Math.min(MAX_SPEED_MULTIPLIER, 1 + speed * VELOCITY_SCALE);
}

function stopMomentum() {
  if (momentumRaf) {
    cancelAnimationFrame(momentumRaf);
    momentumRaf = 0;
  }
  momentumResizeObserver?.disconnect();
  momentumResizeObserver = null;
  momentumEl = null;
  momentumVelocity = 0;
}

function applyEdgePhysics(el: HTMLElement, velocity: number): number {
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
  let nextVelocity = velocity;

  if (el.scrollTop < 0) {
    el.scrollTop = 0;
    if (nextVelocity > 0) nextVelocity *= 0.4;
  }
  if (el.scrollTop > maxScroll) {
    el.scrollTop = maxScroll;
  }

  const distFromBottom = maxScroll - el.scrollTop;
  const scrollingTowardBottom = nextVelocity < 0;
  const nearEnd = nearEndThresholdPx(el);

  if (scrollingTowardBottom && distFromBottom < nearEnd) {
    dispatchNearEnd(el);
  }

  if (scrollingTowardBottom && distFromBottom <= 1) {
    if (hasMoreInfiniteContent(el)) {
      // 추가 로딩 가능 — 관성 유지 (콘텐츠 늘어나면 ResizeObserver가 이어서 스크롤)
      nextVelocity *= 0.985;
    } else {
      nextVelocity *= 0.35;
    }
  } else if (el.scrollTop <= 0 && nextVelocity > 0) {
    nextVelocity *= 0.4;
  }

  return nextVelocity;
}

function startMomentum(el: HTMLElement, velocityPxPerMs: number) {
  stopMomentum();
  if (prefersReducedMotion()) return;
  if (Math.abs(velocityPxPerMs) < MOMENTUM_MIN_VELOCITY) return;

  momentumEl = el;
  momentumVelocity = velocityPxPerMs;
  momentumLastTime = performance.now();

  momentumResizeObserver = new ResizeObserver(() => {
    if (!momentumEl || Math.abs(momentumVelocity) < MOMENTUM_MIN_VELOCITY) return;
    const maxScroll = Math.max(0, momentumEl.scrollHeight - momentumEl.clientHeight);
    if (momentumVelocity < 0 && maxScroll - momentumEl.scrollTop > 4) {
      // 새 항목 로드로 scrollHeight 증가 — 관성 재개
      if (!momentumRaf) {
        momentumRaf = requestAnimationFrame(tick);
      }
    }
  });
  momentumResizeObserver.observe(el);

  function tick(now: number) {
    if (!momentumEl) return;

    const dt = Math.max(now - momentumLastTime, 1);
    momentumLastTime = now;

    momentumEl.scrollTop -= momentumVelocity * dt * MOMENTUM_GAIN;
    momentumVelocity *= Math.pow(MOMENTUM_FRICTION, dt / 16);
    momentumVelocity = applyEdgePhysics(momentumEl, momentumVelocity);

    if (Math.abs(momentumVelocity) < MOMENTUM_MIN_VELOCITY) {
      stopMomentum();
      return;
    }

    momentumRaf = requestAnimationFrame(tick);
  }

  momentumRaf = requestAnimationFrame(tick);
}

function cancelDrag(keepSuppressClick = false) {
  if (!dragState) return;
  if (
    dragState.moved
    && keepSuppressClick
    && Math.abs(dragState.totalDelta) >= CLICK_SUPPRESS_PX
  ) {
    suppressClick = true;
  }
  clearDragStyle(dragState.scrollEl);
  dragState = null;
}

/** 무한 스크롤 컨테이너에 더 불러올 항목이 있는지 표시 */
export function setInfiniteScrollActive(el: HTMLElement | null, hasMore: boolean) {
  if (!el) return;
  if (hasMore) {
    el.dataset.infiniteScroll = "active";
  } else {
    delete el.dataset.infiniteScroll;
  }
}

export { INFINITE_SCROLL_NEAR_END };

export function useInfiniteScrollNearEnd(
  scrollEl: HTMLElement | null,
  hasMore: boolean,
  onNearEnd: () => void,
) {
  useEffect(() => {
    setInfiniteScrollActive(scrollEl, hasMore);
  }, [scrollEl, hasMore]);

  useEffect(() => {
    if (!scrollEl) return;
    const handler = () => onNearEnd();
    scrollEl.addEventListener(INFINITE_SCROLL_NEAR_END, handler);
    return () => scrollEl.removeEventListener(INFINITE_SCROLL_NEAR_END, handler);
  }, [scrollEl, onNearEnd]);
}

export function useGlobalDragScroll() {
  useEffect(() => {
    const onDragStart = (e: DragEvent) => {
      if (e.target instanceof HTMLImageElement) {
        e.preventDefault();
      }
    };

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0 || e.isPrimary === false) return;
      stopMomentum();
      if (shouldIgnoreTarget(e.target)) return;
      if (isTextSelectionTarget(e.target)) return;

      const scrollEl = findScrollableAncestor(resolveElement(e.target));
      if (!scrollEl) return;

      const now = performance.now();
      dragState = {
        scrollEl,
        startY: e.clientY,
        lastY: e.clientY,
        lastTime: now,
        velocity: 0,
        active: false,
        moved: false,
        totalDelta: 0,
      };
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!dragState) return;

      const dy = e.clientY - dragState.lastY;
      const totalDelta = e.clientY - dragState.startY;
      dragState.totalDelta = totalDelta;

      if (!dragState.active) {
        if (Math.abs(totalDelta) < DRAG_THRESHOLD_PX) return;
        dragState.active = true;
        dragState.moved = true;
        dragState.scrollEl.style.cursor = "grabbing";
        dragState.scrollEl.style.userSelect = "none";
      }

      const now = performance.now();
      const dt = Math.max(now - dragState.lastTime, 1);
      const instantVelocity = dy / dt;
      dragState.velocity =
        dragState.velocity * (1 - VELOCITY_SMOOTHING) + instantVelocity * VELOCITY_SMOOTHING;

      const multiplier = speedMultiplier(dragState.velocity);
      dragState.scrollEl.scrollTop -= dy * multiplier;
      maybeDispatchNearEnd(dragState.scrollEl, dragState.velocity);

      dragState.lastY = e.clientY;
      dragState.lastTime = now;

      e.preventDefault();
    };

    const endDrag = () => {
      if (!dragState) return;
      const { scrollEl, velocity, moved, active } = dragState;
      cancelDrag(true);
      if (active && moved) {
        startMomentum(scrollEl, velocity);
      }
    };

    const onClickCapture = (e: MouseEvent) => {
      if (!suppressClick) return;
      const el = resolveElement(e.target);
      if (el?.closest('[role="button"], button, a, [data-poster-card]')) {
        suppressClick = false;
        return;
      }
      suppressClick = false;
      e.preventDefault();
      e.stopPropagation();
    };

    document.addEventListener("dragstart", onDragStart);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("pointermove", onPointerMove, { passive: false });
    document.addEventListener("pointerup", endDrag);
    document.addEventListener("pointercancel", endDrag);
    document.addEventListener("click", onClickCapture, true);

    return () => {
      document.removeEventListener("dragstart", onDragStart);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", endDrag);
      document.removeEventListener("pointercancel", endDrag);
      document.removeEventListener("click", onClickCapture, true);
      clearDragStyle(dragState?.scrollEl ?? null);
      dragState = null;
      stopMomentum();
    };
  }, []);
}
