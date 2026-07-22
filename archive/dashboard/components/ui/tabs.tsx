"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** Segmented control. Controlled: pass value + onChange. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div
      role="tablist"
      className="inline-flex items-center gap-0.5 rounded-lg border border-white/10 bg-white/[0.03] p-0.5"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              "relative rounded-md px-3 py-1 text-xs font-medium transition-colors duration-150",
              active ? "text-black" : "text-muted hover:text-white/90"
            )}
          >
            {active && (
              <motion.span
                layoutId="segmented-active"
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className="absolute inset-0 rounded-md bg-white"
              />
            )}
            <span className="relative">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
