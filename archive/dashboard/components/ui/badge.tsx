import { cn } from "@/lib/utils";

type Variant = "live" | "syncing" | "neutral";

export function Badge({
  variant = "neutral",
  children,
  className,
}: {
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        variant === "live" && "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
        variant === "syncing" && "border-amber-500/20 bg-amber-500/10 text-amber-400",
        variant === "neutral" && "border-white/10 bg-white/[0.04] text-muted",
        className
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          variant === "live" && "bg-emerald-400",
          variant === "syncing" && "animate-pulse bg-amber-400",
          variant === "neutral" && "bg-white/30"
        )}
      />
      {children}
    </span>
  );
}
