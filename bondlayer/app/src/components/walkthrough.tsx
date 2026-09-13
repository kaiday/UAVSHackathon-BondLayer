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
    title: "Welcome to the merchant console",
    body: "BondLayer shows your catalogue the way an AI shopping agent reads it: what it can filter on, what it can't, and why you win or lose a comparison. This tour takes about a minute.",
  },
  {
    target: "nav-overview",
    placement: "right",
    title: "Overview",
    body: "Your home page. It shows catalogue readiness for the selected merchant, the fixes that matter most, and how you compare with the other merchants.",
  },
  {
    target: "comparison",
    placement: "bottom",
    title: "Merchant comparison",
    body: "One card per merchant on the server, with its readiness score and how many blockers its product export contains.",
  },
  {
    target: "readiness",
    placement: "bottom",
    badge: "The number to watch",
    title: "Agent readiness",
    body: "Out of 100, how much of your feed an AI agent can actually act on. Every problem in your export costs points, and blockers cost the most. A blocker is something like a price written as text, which drops the product out of an “under $1,500” filter. Raise this and agents stop skipping your products.",
  },
  {
    target: "worst-first",
    placement: "top",
    title: "Worst first",
    body: "Your to-do list, sorted by how badly each problem hurts you with agents. Start at the top: each row says what an agent does with that field today.",
  },
  {
    target: "nav-catalogue",
    placement: "right",
    title: "Catalogue",
    body: "Every problem found in your product export. Filter by severity, and compare what you published (Found) with what BondLayer cleaned it to (Normalised).",
  },
  {
    target: "nav-requests",
    placement: "right",
    title: "Request console",
    body: "30 shopper requests an agent might send, like “a laptop under $1,500 I can return easily”. For each one, see which merchant won, how much of your verified benefit value was credited, and why you lost.",
  },
  {
    target: "nav-quality",
    placement: "right",
    title: "Data quality",
    body: "The same problems grouped by rule, such as price format or RAM units, so you can fix a whole class of errors in your export at once.",
  },
  {
    target: "nav-benefits",
    placement: "right",
    title: "Benefit records",
    body: "Signed offers such as free returns, warranty and loyalty points that agents can verify before they choose. In this prototype their value shows up in the Request console.",
  },
  {
    target: "search",
    placement: "bottom",
    title: "Search",
    body: "Find a request or a product by name. Preview: not connected in this prototype.",
  },
  {
    target: "prompt",
    placement: "top",
    title: "Ask BondLayer",
    body: "Ask in plain language, for example “Why did I lose this request?” or “What should I fix first?”. Preview: not connected to a model in this prototype.",
  },
  {
    target: "help",
    placement: "bottom",
    title: "Replay this tour",
    body: "Click the help icon any time to see this walkthrough again.",
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
