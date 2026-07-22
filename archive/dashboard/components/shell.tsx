"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { KeyRound, LayoutGrid, Network, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid },
  { href: "/keys", label: "API Keys", icon: KeyRound },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const nav = (horizontal: boolean) => (
    <nav
      className={cn(
        horizontal ? "flex items-center gap-1" : "flex flex-col gap-0.5"
      )}
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors duration-150",
              active
                ? "bg-white/[0.07] font-medium text-white"
                : "text-muted hover:bg-white/[0.04] hover:text-white/90"
            )}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-dvh">
      {/* ── desktop sidebar ─────────────────────────────────────── */}
      <aside className="sticky top-0 hidden h-dvh w-56 shrink-0 flex-col border-r border-white/10 px-3 py-4 md:flex">
        <Link href="/" className="mb-6 flex items-center gap-2 px-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-white">
            <Network className="h-3 w-3 text-black" strokeWidth={2} />
          </span>
          <span className="text-[13px] font-semibold tracking-tight text-white">
            CodeCortex
          </span>
        </Link>
        {nav(false)}
        <div className="mt-auto border-t border-white/10 px-2 pt-3">
          <p className="text-xs text-muted">acme-corp</p>
          <p className="mt-0.5 text-[11px] text-faint">Free plan · us-east</p>
        </div>
      </aside>

      {/* ── mobile top bar ──────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex items-center justify-between border-b border-white/10 bg-black/80 px-4 py-2.5 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-white">
              <Network className="h-3 w-3 text-black" strokeWidth={2} />
            </span>
            <span className="text-[13px] font-semibold text-white">CodeCortex</span>
          </Link>
          {nav(true)}
        </header>

        <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 md:px-8 md:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
