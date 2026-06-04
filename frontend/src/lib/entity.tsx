import {
  GitPullRequest,
  Server,
  User,
  FileText,
  FolderGit2,
  Ticket,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { EntityType } from "@/types/trace";

export interface EntityStyle {
  icon: LucideIcon;
  /** Tailwind classes for the soft node chip (inactive resting state). */
  chip: string;
  /** Icon color. */
  iconColor: string;
  /** Badge variant key for shadcn Badge. */
  badge:
    | "indigo"
    | "slate"
    | "amber"
    | "zinc"
    | "emerald"
    | "rose";
  label: string;
}

/**
 * Maps each entity type to a lucide icon + tasteful soft-color chip:
 *   PRs indigo-tinted · Services slate · People amber · Docs zinc.
 */
export const ENTITY_STYLES: Record<EntityType, EntityStyle> = {
  PR: {
    icon: GitPullRequest,
    chip: "bg-indigo-50 border-indigo-100",
    iconColor: "text-indigo-600",
    badge: "indigo",
    label: "Pull Request",
  },
  Service: {
    icon: Server,
    chip: "bg-slate-50 border-slate-200",
    iconColor: "text-slate-500",
    badge: "slate",
    label: "Service",
  },
  Person: {
    icon: User,
    chip: "bg-amber-50 border-amber-100",
    iconColor: "text-amber-600",
    badge: "amber",
    label: "Person",
  },
  Document: {
    icon: FileText,
    chip: "bg-zinc-50 border-zinc-200",
    iconColor: "text-zinc-500",
    badge: "zinc",
    label: "Document",
  },
  Repo: {
    icon: FolderGit2,
    chip: "bg-violet-50 border-violet-100",
    iconColor: "text-violet-600",
    badge: "indigo",
    label: "Repository",
  },
  Ticket: {
    icon: Ticket,
    chip: "bg-sky-50 border-sky-100",
    iconColor: "text-sky-600",
    badge: "slate",
    label: "Ticket",
  },
  Team: {
    icon: Users,
    chip: "bg-amber-50 border-amber-100",
    iconColor: "text-amber-600",
    badge: "amber",
    label: "Team",
  },
  Tool: {
    icon: Wrench,
    chip: "bg-emerald-50 border-emerald-100",
    iconColor: "text-emerald-600",
    badge: "emerald",
    label: "Tool",
  },
};
