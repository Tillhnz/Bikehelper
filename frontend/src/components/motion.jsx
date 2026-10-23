import { useEffect, useRef, useState } from "react";
import { fmtNum } from "../api.js";

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Gleitet von der letzten Zahl zur neuen. Bei reduzierter Bewegung springt der Wert sofort. */
export function useTween(target, ms = 650) {
  const [value, setValue] = useState(target ?? 0);
  const from = useRef(target ?? 0);
  const raf = useRef(0);

  useEffect(() => {
    if (target == null || Number.isNaN(target)) return undefined;
    if (prefersReducedMotion()) {
      from.current = target;
      setValue(target);
      return undefined;
    }
    const start = performance.now();
    const origin = from.current;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = origin + (target - origin) * eased;
      from.current = v;
      setValue(v);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, ms]);

  return value;
}

/** Zahl, die beim Ändern zum neuen Wert hochzählt. */
export function CountUp({ value, digits = 0, ms = 650 }) {
  const v = useTween(value, ms);
  return <>{value == null ? "–" : fmtNum(v, digits)}</>;
}

/** Blendet Kinder erst ein, wenn sie in den sichtbaren Bereich kommen (einmalig). */
export function useInView(ref) {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return undefined;
    if (!("IntersectionObserver" in window) || prefersReducedMotion()) {
      setSeen(true);
      return undefined;
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setSeen(true);
        io.disconnect();
      }
    }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, seen]);
  return seen;
}
