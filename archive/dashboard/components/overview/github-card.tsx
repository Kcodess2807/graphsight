"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Github, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";

interface Repo {
  name: string;
  nodes: string;
  lastEvent: string;
  status: "live" | "syncing";
}

const REPOS: Repo[] = [
  { name: "tiangolo/fastapi", nodes: "412,882", lastEvent: "2m ago · push", status: "live" },
  { name: "acme-corp/platform", nodes: "689,102", lastEvent: "14m ago · pr merged", status: "live" },
  { name: "acme-corp/billing-service", nodes: "121,406", lastEvent: "1h ago · issue linked", status: "live" },
  { name: "acme-corp/infra", nodes: "61,112", lastEvent: "indexing history…", status: "syncing" },
];

export function GithubCard({ initialConnected }: { initialConnected: boolean }) {
  const [connected, setConnected] = useState(initialConnected);

  return (
    <Card className={connected ? undefined : "animate-glow border-transparent"}>
      <CardHeader
        title="GitHub"
        description={
          connected
            ? "App installed. Webhooks stream PRs, issues, and commits into your graph."
            : "Install the CodeCortex GitHub App to start building your graph."
        }
        action={
          connected ? (
            <Button variant="ghost" size="sm" onClick={() => setConnected(false)}>
              Disconnect
            </Button>
          ) : undefined
        }
      />

      <AnimatePresence mode="wait" initial={false}>
        {!connected ? (
          <motion.div
            key="disconnected"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col items-center gap-3 px-4 py-10 text-center"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
              <Github className="h-5 w-5 text-white/80" strokeWidth={1.5} />
            </span>
            <p className="max-w-sm text-xs leading-relaxed text-muted">
              CodeCortex reads PRs, issues, and commit history — never your
              secrets. Permissions are read-only and scoped per repository.
            </p>
            <a href="/api/github/login">
              <Button variant="primary">
                <Github className="h-3.5 w-3.5" />
                Connect GitHub App
              </Button>
            </a>
          </motion.div>
        ) : (
          <motion.div
            key="connected"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-white/10 text-[11px] uppercase tracking-wide text-faint">
                  <th className="px-4 py-2 font-medium">Repository</th>
                  <th className="hidden px-4 py-2 font-medium sm:table-cell">Nodes</th>
                  <th className="hidden px-4 py-2 font-medium md:table-cell">Last event</th>
                  <th className="px-4 py-2 font-medium">Sync status</th>
                </tr>
              </thead>
              <tbody>
                {REPOS.map((repo) => (
                  <tr
                    key={repo.name}
                    className="border-b border-white/[0.06] transition-colors duration-150 last:border-0 hover:bg-white/[0.03]"
                  >
                    <td className="px-4 py-2.5 font-mono text-xs text-white/90">
                      {repo.name}
                    </td>
                    <td className="hidden px-4 py-2.5 font-mono text-xs tabular-nums text-muted sm:table-cell">
                      {repo.nodes}
                    </td>
                    <td className="hidden px-4 py-2.5 text-xs text-muted md:table-cell">
                      {repo.lastEvent}
                    </td>
                    <td className="px-4 py-2.5">
                      {repo.status === "live" ? (
                        <Badge variant="live">Live (Webhook active)</Badge>
                      ) : (
                        <Badge variant="syncing">Syncing…</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-white/10 px-4 py-2.5">
              <Button variant="ghost" size="sm">
                <Plus className="h-3.5 w-3.5" />
                Add repository
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}
