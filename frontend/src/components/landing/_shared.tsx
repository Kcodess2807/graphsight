// Landing design tokens + the two wrappers every section uses.
// Light neubrutalist: white page, #131316 ink, hard offset shadows,
// lime marker-highlights, emerald interactive accents.
import type { ReactNode } from "react";
import { motion } from "framer-motion";

export const CARD =
  "rounded-xl border border-[#131316] bg-white shadow-[3px_4px_0_0_#131316]";
export const BTN_PRIMARY =
  "rounded-lg bg-[#131316] font-semibold text-white transition-colors duration-150 hover:bg-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#131316]";
export const LIME = "#C8F169";
export const EMERALD = "#059669";

export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.1 }}
      transition={{ duration: 0.45, delay, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function SectionHead({
  eyebrow,
  title,
  sub,
}: {
  eyebrow?: string;
  title: string;
  sub?: string;
}) {
  return (
    <Reveal className="mx-auto max-w-2xl text-center">
      {eyebrow && (
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-600">{eyebrow}</p>
      )}
      <h2 className="mt-3 font-display text-3xl font-bold leading-tight tracking-[-0.02em] text-[#131316] sm:text-4xl">
        {title}
      </h2>
      {sub && <p className="mt-3 text-[15px] leading-relaxed text-zinc-600">{sub}</p>}
    </Reveal>
  );
}
