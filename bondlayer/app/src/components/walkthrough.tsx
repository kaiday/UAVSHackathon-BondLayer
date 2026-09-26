"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";

/**
 * First-visit tour of the console. Each step points a popover at an element
 * marked `data-tour="…"`; everything else is blurred. A step whose target is
 * not on screen (still loading, or hidden on a narrow viewport) is shown as a
 * centred card instead of pointing at nothing.
 *
 * The copy describes what each part does. It quotes no figures: numbers only
 * ever come from the API (see lib/api.ts).
 */

type Placement = "right" | "left" | "top" | "bottom";

type Step = {
  target?: string;
  placement?: Placement;
  badge?: string;
  title: string;
  body: string;
};

const STEPS: Step[] = [
  {
    title: "Welcome to BondLayer",
    body: "See how AI shopping agents read your catalogue, and what to fix. Takes a minute.",
  },
  {
    target: "nav-overview",
    placement: "right",
    title: "Overview",
    body: "Your readiness score, top fixes, and how you compare.",
  },
  {
    target: "comparison",
    placement: "bottom",
    title: "Your merchants",
    body: "Click a merchant to view it. Show all merchants lists the rest.",
  },
  {
    target: "readiness",
    placement: "bottom",
    badge: "Key number",
    title: "Agent readiness",
    body: "How much of your catalogue agents can use, out of 100. Blockers cost the most points.",
  },
  {
    target: "worst-first",
    placement: "top",
    title: "Top issues",
    body: "Your most severe problems. Start at the top.",
  },
  {
    target: "nav-catalogue",
    placement: "right",
    title: "Catalogue",
    body: "Every issue, with the fix for each. Filter by severity.",
  },
  {
    target: "nav-requests",
    placement: "right",
    title: "Shopping insights",
    body: "What shoppers asked for, and what to improve.",
  },
  {
    target: "nav-quality",
    placement: "right",
    title: "Data quality",
    body: "Issues grouped by type, so you can fix them in bulk.",
  },
  {
    target: "nav-benefits",
    placement: "right",
    title: "Benefit records",
    body: "Publish returns, warranty and loyalty benefits that agents can verify.",
  },
  {
    target: "prompt",
    placement: "top",
    title: "Ask BondLayer",
    body: "Ask about your catalogue, e.g. “What should I fix first?”",
  },
  {
    target: "help",
    placement: "bottom",
    title: "Replay this tour",
    body: "Click here any time to see this tour again.",
  },
];

const SEEN_KEY = "bondlayer.console.tour.seen";
const GAP = 14;
const MARGIN = 16;
const PAD = 6;

type Rect = { top: number; left: number; width: number; height: number };

export function hasSeenTour(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Private windows: the tour just shows again next visit.
  }
}

function measure(target: string | undefined): Rect | null {
  if (!target) return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return null;
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 };
}

function sameRect(a: Rect | null, b: Rect | null) {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

/** Where the popover goes, flipped and clamped so it stays on screen. */
function place(rect: Rect, preferred: Placement, w: number, h: number) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const fits: Record<Placement, boolean> = {
    right: rect.left + rect.width + GAP + w <= vw - MARGIN,
    left: rect.left - GAP - w >= MARGIN,
    bottom: rect.top + rect.height + GAP + h <= vh - MARGIN,
    top: rect.top - GAP - h >= MARGIN,
  };
  const opposite: Record<Placement, Placement> = { right: "left", left: "right", top: "bottom", bottom: "top" };
  const order: Placement[] = [preferred, opposite[preferred], "bottom", "top", "right", "left"];
  const side = order.find((p) => fits[p]);

  const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(v, max));
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;

  // A target taller or wider than the room around it (a long table): sit the
  // popover inside its visible top-right corner instead of off screen.
  if (!side) {
    const top = clamp(Math.max(rect.top, 0) + 64, MARGIN, vh - MARGIN - h);
    const left = clamp(Math.min(rect.left + rect.width, vw) - w - 24, MARGIN, vw - MARGIN - w);
    return { side: "inside" as const, top, left, arrow: null };
  }

  let top: number;
  let left: number;
  if (side === "right" || side === "left") {
    left = side === "right" ? rect.left + rect.width + GAP : rect.left - GAP - w;
    top = clamp(cy - h / 2, MARGIN, vh - MARGIN - h);
  } else {
    top = side === "bottom" ? rect.top + rect.height + GAP : rect.top - GAP - h;
    left = clamp(cx - w / 2, MARGIN, vw - MARGIN - w);
  }
  // The arrow points at the target's centre, kept inside the popover's corners.
  const arrow =
    side === "right" || side === "left"
      ? { top: clamp(cy - top, 18, h - 18) }
      : { left: clamp(cx - left, 18, w - 18) };
  return { side, top, left, arrow };
}

export function Walkthrough({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [size, setSize] = useState({ w: 340, h: 200 });
  const sizeRef = useRef(size);
  const popoverRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const scrolledFor = useRef<number>(-1);

  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  // Reset on the way out, so the next open starts from the welcome card.
  const close = useCallback(() => {
    markSeen();
    setIndex(0);
    scrolledFor.current = -1;
    onClose();
  }, [onClose]);

  const next = useCallback(() => {
    if (last) close();
    else setIndex((i) => i + 1);
  }, [last, close]);

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  // Follow the target every frame: it may still be loading, the page may
  // scroll, or the window may resize.
  useEffect(() => {
    if (!open) return;
    let frame = 0;
    let current: Rect | null = null;
    const tick = () => {
      const measured = measure(step.target);
      if (measured && scrolledFor.current !== index) {
        scrolledFor.current = index;
        const el = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
        const r = el?.getBoundingClientRect();
        if (el && r && (r.top < 80 || r.bottom > window.innerHeight - 120)) {
          el.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }
      if (!sameRect(measured, current)) {
        current = measured;
        setRect(measured);
      }
      // The popover's own size decides whether it fits beside the target.
      const pop = popoverRef.current;
      if (pop && (pop.offsetWidth !== sizeRef.current.w || pop.offsetHeight !== sizeRef.current.h)) {
        sizeRef.current = { w: pop.offsetWidth, h: pop.offsetHeight };
        setSize(sizeRef.current);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [open, index, step.target]);

  useEffect(() => {
    if (open) nextRef.current?.focus({ preventScroll: true });
  }, [open, index]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      else if (event.key === "ArrowRight") next();
      else if (event.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close, next, back]);

  if (!open) return null;

  const placed = rect ? place(rect, step.placement ?? "bottom", size.w, size.h) : null;
  const popoverStyle = placed ? { top: placed.top, left: placed.left } : undefined;

  return (
    <div className="tour-root">
      {rect ? (
        <>
          <div className="tour-shade" style={{ top: 0, left: 0, right: 0, height: Math.max(0, rect.top) }} />
          <div className="tour-shade" style={{ top: rect.top + rect.height, left: 0, right: 0, bottom: 0 }} />
          <div className="tour-shade" style={{ top: rect.top, left: 0, width: Math.max(0, rect.left), height: rect.height }} />
          <div className="tour-shade" style={{ top: rect.top, left: rect.left + rect.width, right: 0, height: rect.height }} />
          <div className="tour-spotlight" style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }} />
        </>
      ) : (
        <div className="tour-shade" style={{ inset: 0 }} />
      )}

      <div
        ref={popoverRef}
        className={`tour-popover ${placed ? `side-${placed.side}` : "centred"}`}
        style={popoverStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        key={index}
      >
        {placed?.arrow && <span className="tour-arrow" style={placed.arrow} aria-hidden="true" />}
        <div className="tour-meta">
          <span>
            Step {index + 1} of {STEPS.length}
          </span>
          {step.badge && <b className="tour-badge">{step.badge}</b>}
        </div>
        <h2 id="tour-title">{step.title}</h2>
        <p id="tour-body">{step.body}</p>
        <div className="tour-footer">
          <div className="tour-dots" aria-hidden="true">
            {STEPS.map((_, i) => (
              <i key={i} className={i === index ? "on" : ""} />
            ))}
          </div>
          <div className="tour-buttons">
            {index > 0 && (
              <button type="button" className="tour-back" onClick={back}>
                <ArrowLeft size={14} strokeWidth={2.2} aria-hidden="true" /> Back
              </button>
            )}
            <button type="button" className="tour-next" onClick={next} ref={nextRef}>
              {index === 0 ? "Start tour" : last ? "Finish" : "Next"}
              {!last && <ArrowRight size={14} strokeWidth={2.2} aria-hidden="true" />}
            </button>
          </div>
        </div>
      </div>

      {!last && (
        <button type="button" className="tour-skip" onClick={close}>
          Skip tour <X size={14} strokeWidth={2.2} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
