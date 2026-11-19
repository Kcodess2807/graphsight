import { cn } from "@/lib/utils";

// a lowercase g drawn as a graph: one node, one edge, and the node it remembers.
// keep in sync with public/favicon.svg
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("h-7 w-7 shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill="#131316" />
      <g fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round">
        <circle cx="14.5" cy="13" r="5" />
        <path d="M21 7.5V19a5.5 5.5 0 0 1-5.5 5.5h-1" />
      </g>
      <circle cx="10.5" cy="24.5" r="3" fill="#C8F169" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-[15px] font-bold tracking-tight text-[#131316]">Graphsight</span>
    </div>
  );
}
