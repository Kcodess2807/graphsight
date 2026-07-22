"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Segmented } from "@/components/ui/tabs";

const USED = 85_000;
const LIMIT = 100_000;

const USAGE_ROWS = [
  { label: "GitHub ingestion", value: "61,204 nodes" },
  { label: "Jira ingestion", value: "18,911 nodes" },
  { label: "Manual uploads", value: "4,885 nodes" },
];

const PRO_FEATURES = [
  "1,000,000 nodes / month",
  "Unlimited repositories",
  "Priority webhook lanes",
  "SSO & audit log",
];

type Tab = "usage" | "billing";

export function SettingsTabs() {
  const [tab, setTab] = useState<Tab>("usage");

  return (
    <div className="space-y-4">
      <Segmented<Tab>
        options={[
          { value: "usage", label: "Usage" },
          { value: "billing", label: "Billing" },
        ]}
        value={tab}
        onChange={setTab}
      />

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15, ease: "easeOut" }}
        >
          {tab === "usage" ? <UsagePanel /> : <BillingPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function UsagePanel() {
  return (
    <Card>
      <CardHeader
        title="Node usage"
        description="Resets on the 1st of each month."
      />
      <div className="px-4 py-4">
        <div className="flex items-baseline justify-between">
          <p className="font-mono text-sm tabular-nums text-white">
            {USED.toLocaleString("en-US")}{" "}
            <span className="text-muted">/ {LIMIT.toLocaleString("en-US")} nodes used</span>
          </p>
          <p className="text-[11px] text-faint">85%</p>
        </div>
        <Progress value={USED} max={LIMIT} className="mt-2.5" />
        <p className="mt-2.5 text-[11px] text-faint">
          At the current ingestion rate you will hit the limit in ~6 days.
          Overflow events are queued, not dropped.
        </p>
      </div>
      <div className="border-t border-white/10">
        {USAGE_ROWS.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5 last:border-0"
          >
            <p className="text-xs text-muted">{row.label}</p>
            <p className="font-mono text-xs tabular-nums text-white/90">{row.value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BillingPanel() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Card className="px-4 py-4">
        <p className="text-xs text-muted">Current plan</p>
        <p className="mt-1 text-base font-semibold text-white">Free</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          100,000 nodes per month, 5 repositories, community support. Fine for
          evaluating; teams outgrow it fast.
        </p>
      </Card>

      <Card className="relative overflow-hidden px-4 py-4">
        <div className="flex items-baseline justify-between">
          <p className="text-xs text-muted">Upgrade</p>
          <p className="font-mono text-xs text-muted">
            <span className="text-base font-semibold text-white">$49</span>/mo
          </p>
        </div>
        <p className="mt-1 text-base font-semibold text-white">Pro</p>
        <ul className="mt-3 space-y-1.5">
          {PRO_FEATURES.map((f) => (
            <li key={f} className="flex items-center gap-2 text-xs text-muted">
              <Check className="h-3.5 w-3.5 text-emerald-400" strokeWidth={2} />
              {f}
            </li>
          ))}
        </ul>
        <Button variant="primary" className="mt-4 w-full">
          Upgrade to Pro
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Button>
      </Card>
    </div>
  );
}
