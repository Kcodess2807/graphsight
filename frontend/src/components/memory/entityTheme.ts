// Dual-theme entity styling for the memory layer. Light mode uses 600-weight
// hues on paper; dark mode (via the `dark` class on AppLayout's root) uses
// 300-weight hues on the void. Wells stay at 10–15% alpha in both.
// Classes are written out literally — Tailwind's JIT cannot see composed names.
import {
  GitPullRequest,
  Server,
  User,
  FileText,
  FolderGit2,
  Library,
  Ticket,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { EntityType } from "@/types/trace";

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
    well: "bg-indigo-500/10 border-indigo-500/20 dark:bg-indigo-500/15 dark:border-indigo-400/25",
    glyph: "text-indigo-600 dark:text-indigo-300",
    text: "text-indigo-600 dark:text-indigo-300",
    label: "Pull Request",
  },
  Service: {
    icon: Server,
    well: "bg-slate-500/10 border-slate-500/20 dark:bg-slate-400/15 dark:border-slate-400/25",
    glyph: "text-slate-600 dark:text-slate-300",
    text: "text-slate-600 dark:text-slate-300",
    label: "Service",
  },
  Person: {
    icon: User,
    well: "bg-amber-500/10 border-amber-500/20 dark:bg-amber-500/15 dark:border-amber-400/25",
    glyph: "text-amber-600 dark:text-amber-300",
    text: "text-amber-600 dark:text-amber-300",
    label: "Person",
  },
  Document: {
    icon: FileText,
    well: "bg-zinc-500/10 border-zinc-500/20 dark:bg-zinc-400/15 dark:border-zinc-400/25",
    glyph: "text-zinc-600 dark:text-zinc-300",
    text: "text-zinc-600 dark:text-zinc-300",
    label: "Document",
  },
  Repo: {
    icon: FolderGit2,
    well: "bg-violet-500/10 border-violet-500/20 dark:bg-violet-500/15 dark:border-violet-400/25",
    glyph: "text-violet-600 dark:text-violet-300",
    text: "text-violet-600 dark:text-violet-300",
    label: "Repository",
  },
  Library: {
    icon: Library,
    well: "bg-rose-500/10 border-rose-500/20 dark:bg-rose-500/15 dark:border-rose-400/25",
    glyph: "text-rose-600 dark:text-rose-300",
    text: "text-rose-600 dark:text-rose-300",
    label: "Library",
  },
  Ticket: {
    icon: Ticket,
    well: "bg-sky-500/10 border-sky-500/20 dark:bg-sky-500/15 dark:border-sky-400/25",
    glyph: "text-sky-600 dark:text-sky-300",
    text: "text-sky-600 dark:text-sky-300",
    label: "Ticket",
  },
  Team: {
    icon: Users,
    well: "bg-amber-500/10 border-amber-500/20 dark:bg-amber-500/15 dark:border-amber-400/25",
    glyph: "text-amber-600 dark:text-amber-300",
    text: "text-amber-600 dark:text-amber-300",
    label: "Team",
  },
  Tool: {
    icon: Wrench,
    well: "bg-emerald-500/10 border-emerald-500/20 dark:bg-emerald-500/15 dark:border-emerald-400/25",
    glyph: "text-emerald-600 dark:text-emerald-300",
    text: "text-emerald-600 dark:text-emerald-300",
    label: "Tool",
  },
};
