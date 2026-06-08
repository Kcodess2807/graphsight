import { useEffect, useRef, useState } from "react";
import { animate } from "framer-motion";

interface NumberTickerProps {
  value: number;
  decimals?: number;
  durationMs?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  group?: boolean;
}

// animated number ticker that counts up to `value` once it scrolls into view
export function NumberTicker({
  value,
  decimals = 0,
  durationMs = 1100,
  prefix = "",
  suffix = "",
  className,
  group = false,
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [display, setDisplay] = useState(0);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const controls = animate(0, value, {
            duration: durationMs / 1000,
            ease: [0.16, 1, 0.3, 1],
            onUpdate: (v) => setDisplay(v),
          });
          return () => controls.stop();
        }
      },
      { threshold: 0.4 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [value, durationMs]);

  const formatted = group
    ? display.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : display.toFixed(decimals);

  return (
    <span ref={ref} className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
