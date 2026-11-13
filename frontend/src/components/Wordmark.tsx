import { Terminal } from "lucide-react";
import { cn } from "@/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#131316]">
        <Terminal className="h-3.5 w-3.5 text-white" strokeWidth={2} />
      </span>
      <span className="text-[15px] font-bold tracking-tight text-[#131316]">Graphsight</span>
    </div>
  );
}
