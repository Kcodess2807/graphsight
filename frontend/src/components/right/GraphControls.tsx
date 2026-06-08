import {
  ZoomIn,
  ZoomOut,
  Locate,
  EyeOff,
  Eye,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface GraphControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onRecenter: () => void;
  showContext: boolean;
  onToggleContext: (v: boolean) => void;
  hiddenCount: number;
  // optional: when omitted (mobile) the full-graph focus button isn't rendered
  graphFocus?: boolean;
  onToggleFocus?: () => void;
}

export function GraphControls({
  onZoomIn,
  onZoomOut,
  onRecenter,
  showContext,
  onToggleContext,
  hiddenCount,
  graphFocus,
  onToggleFocus,
}: GraphControlsProps) {
  return (
    <div className="glass flex items-center gap-0.5 rounded-full border border-white/60 p-1 shadow-lifted ring-1 ring-black/[0.03]">
      <ControlButton label="Zoom in" onClick={onZoomIn}>
        <ZoomIn />
      </ControlButton>
      <ControlButton label="Zoom out" onClick={onZoomOut}>
        <ZoomOut />
      </ControlButton>
      <ControlButton label="Recenter graph" onClick={onRecenter}>
        <Locate />
      </ControlButton>

      <Separator orientation="vertical" className="mx-0.5 h-5" />

      <Tooltip>
        <TooltipTrigger asChild>
          <Toggle
            size="sm"
            pressed={showContext}
            onPressedChange={onToggleContext}
            aria-label="Show surrounding context"
            className="h-8 gap-1.5 rounded-full px-2.5 data-[state=on]:bg-indigo-50 data-[state=on]:text-indigo-700"
          >
            {showContext ? (
              <Eye className="h-4 w-4" />
            ) : (
              <EyeOff className="h-4 w-4" />
            )}
            <span className="text-xs font-medium">Context</span>
            {!showContext && hiddenCount > 0 && (
              <span className="rounded-full bg-zinc-200/80 px-1.5 font-mono text-[10px] text-zinc-600">
                +{hiddenCount}
              </span>
            )}
          </Toggle>
        </TooltipTrigger>
        <TooltipContent>
          {showContext
            ? "Hide surrounding context — show the traced path only"
            : "Show the surrounding sub-graph"}
        </TooltipContent>
      </Tooltip>

      {onToggleFocus && (
        <>
          <Separator orientation="vertical" className="mx-0.5 h-5" />
          <ControlButton
            label={graphFocus ? "Exit full graph (Esc)" : "Full graph"}
            onClick={onToggleFocus}
          >
            {graphFocus ? <Minimize2 /> : <Maximize2 />}
          </ControlButton>
        </>
      )}
    </div>
  );
}

function ControlButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onClick}
          aria-label={label}
          className="rounded-full text-zinc-500 hover:bg-white hover:text-zinc-900"
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
