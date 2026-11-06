// Entity styling for the memory layer: 600-weight hues in 10% alpha wells.
// Classes are written out literally — Tailwind's JIT cannot see composed names.
import {
  GitCommitHorizontal,
  GitPullRequest,
  Server,
  User,
  FileCode,
  FileText,
  FolderGit2,
  Library,
  Ticket,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { EntityType, TraceNode } from "@/types/trace";

export interface MemoryEntityStyle {
  icon: LucideIcon;
  /* icon well behind the glyph */
  well: string;
  /* the glyph itself */
  glyph: string;
  /* text color for inline mentions / citation pills */
  text: string;
  label: string;
}

export const MEMORY_ENTITY_STYLES: Record<EntityType, MemoryEntityStyle> = {
  PR: {
    icon: GitPullRequest,
    well: "bg-indigo-500/10 border-indigo-500/20",
    glyph: "text-indigo-600",
    text: "text-indigo-600",
    label: "Pull Request",
  },
  Commit: {
    icon: GitCommitHorizontal,
    well: "bg-teal-500/10 border-teal-500/20",
    glyph: "text-teal-600",
    text: "text-teal-700",
    label: "Commit",
  },
  Service: {
    icon: Server,
    well: "bg-slate-500/10 border-slate-500/20",
    glyph: "text-slate-600",
    text: "text-slate-600",
    label: "Service",
  },
  Person: {
    icon: User,
    well: "bg-amber-500/10 border-amber-500/20",
    glyph: "text-amber-600",
    text: "text-amber-700",
    label: "Person",
  },
  Document: {
    icon: FileText,
    well: "bg-zinc-500/10 border-zinc-500/20",
    glyph: "text-zinc-600",
    text: "text-zinc-600",
    label: "Document",
  },
  Repo: {
    icon: FolderGit2,
    well: "bg-violet-500/10 border-violet-500/20",
    glyph: "text-violet-600",
    text: "text-violet-600",
    label: "Repository",
  },
  Library: {
    icon: Library,
    well: "bg-rose-500/10 border-rose-500/20",
    glyph: "text-rose-600",
    text: "text-rose-600",
    label: "Library",
  },
  Ticket: {
    icon: Ticket,
    well: "bg-sky-500/10 border-sky-500/20",
    glyph: "text-sky-600",
    text: "text-sky-700",
    label: "Ticket",
  },
  Team: {
    icon: Users,
    well: "bg-amber-500/10 border-amber-500/20",
    glyph: "text-amber-600",
    text: "text-amber-700",
    label: "Team",
  },
  Tool: {
    icon: Wrench,
    well: "bg-emerald-500/10 border-emerald-500/20",
    glyph: "text-emerald-700",
    text: "text-emerald-700",
    label: "Tool",
  },
  File: {
    icon: FileCode,
    well: "bg-stone-500/10 border-stone-500/20",
    glyph: "text-stone-600",
    text: "text-stone-600",
    label: "File",
  },
};

// traces are user-supplied JSON, so an unknown type must not crash the render
export function entityStyle(type: string): MemoryEntityStyle {
  return MEMORY_ENTITY_STYLES[type as EntityType] ?? MEMORY_ENTITY_STYLES.Document;
}

// the mapper's measured wording when it exists, otherwise only what the trace proves
export function usageLabel(node: Pick<TraceNode, "active" | "meta">): string {
  const measured = node.meta?.subtitle?.match(/^(overlaps the answer|no lexical trace in answer)/);
  return measured?.[1] ?? (node.active ? "in the trace" : "context only");
}

export function formatAge(days: number | null | undefined): string | null {
  if (days == null) return null;
  if (days < 1) return "today";
  return days < 60 ? `${Math.round(days)}d` : `${Math.round(days / 30)}mo`;
}
