import { FadeIn } from "@/components/fade-in";
import { KeyManager } from "@/components/keys/key-manager";
import { Card, CardHeader } from "@/components/ui/card";

const MCP_CONFIG = `{
  "mcpServers": {
    "codecortex": {
      "url": "https://mcp.codecortex.dev/v1",
      "headers": { "Authorization": "Bearer <YOUR_API_KEY>" }
    }
  }
}`;

export default function KeysPage() {
  return (
    <div className="space-y-6">
      <FadeIn>
        <h1 className="text-lg font-semibold tracking-tight text-white">
          API Keys &amp; Access
        </h1>
        <p className="mt-1 max-w-lg text-[13px] text-muted">
          Connect your local MCP server to CodeCortex. Agents authenticate with
          a bearer key — keep it out of version control.
        </p>
      </FadeIn>

      <FadeIn delay={0.08}>
        <KeyManager />
      </FadeIn>

      <FadeIn delay={0.16}>
        <Card>
          <CardHeader
            title="MCP configuration"
            description="Drop this into Claude Code, Cursor, or Windsurf and replace the key."
          />
          <pre className="overflow-x-auto px-4 py-3.5 font-mono text-xs leading-relaxed text-muted">
            {MCP_CONFIG}
          </pre>
        </Card>
      </FadeIn>
    </div>
  );
}
