import { FadeIn } from "@/components/fade-in";
import { GithubCard } from "@/components/overview/github-card";
import { Card } from "@/components/ui/card";

const METRICS = [
  { label: "Total Nodes Ingested", value: "1,284,502", delta: "+12,041 this week" },
  { label: "Active Repositories", value: "12", delta: "3 orgs connected" },
];

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string }>;
}) {
  const { connected } = await searchParams;

  return (
    <div className="space-y-6">
      <FadeIn>
        <h1 className="text-lg font-semibold tracking-tight text-white">
          Overview
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          Your graph at a glance — ingestion, sources, and sync health.
        </p>
      </FadeIn>

      {/* hero metrics */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {METRICS.map((m, i) => (
          <FadeIn key={m.label} delay={0.05 + i * 0.05}>
            <Card className="px-4 py-4">
              <p className="text-xs text-muted">{m.label}</p>
              <p className="mt-1.5 font-mono text-2xl font-medium tabular-nums text-white">
                {m.value}
              </p>
              <p className="mt-1 text-[11px] text-faint">{m.delta}</p>
            </Card>
          </FadeIn>
        ))}
      </div>

      <FadeIn delay={0.18}>
        <GithubCard initialConnected={connected === "1"} />
      </FadeIn>
    </div>
  );
}
