"use client";

import { useState } from "react";
import { Copy, Eye, EyeOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

function generateKey() {
  const alphabet =
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  let suffix = "";
  for (let i = 0; i < 32; i++) {
    suffix += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return `sk_live_cc_${suffix}`;
}

export function KeyManager() {
  const toast = useToast();
  const [key, setKey] = useState(generateKey);
  const [revealed, setRevealed] = useState(false);
  const [rolling, setRolling] = useState(false);

  const masked = `${key.slice(0, 11)}${"•".repeat(24)}${key.slice(-4)}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(key);
      toast("API key copied to clipboard");
    } catch {
      toast("Copy failed — reveal and copy manually");
    }
  };

  const roll = () => {
    setRolling(true);
    // simulate the round-trip; swap for a POST /api/keys/roll call
    setTimeout(() => {
      setKey(generateKey());
      setRolling(false);
      setRevealed(false);
      toast("Key rolled — previous key is now revoked");
    }, 600);
  };

  return (
    <Card>
      <CardHeader
        title="Secret key"
        description="Grants full read access to your graph. Treat it like a password."
        action={
          <Button variant="ghost" size="sm" onClick={roll} disabled={rolling}>
            <RefreshCw className={cn("h-3.5 w-3.5", rolling && "animate-spin")} />
            Roll key
          </Button>
        }
      />
      <div className="flex flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center">
        <code
          className={cn(
            "flex-1 select-all overflow-x-auto whitespace-nowrap rounded-md border border-white/10",
            "bg-black px-3 py-2 font-mono text-xs text-white/90 transition-[filter] duration-200",
            !revealed && "select-none blur-[3px]"
          )}
          aria-label="API key"
        >
          {revealed ? key : masked}
        </code>
        <div className="flex shrink-0 gap-2">
          <Button onClick={() => setRevealed((v) => !v)} aria-pressed={revealed}>
            {revealed ? (
              <EyeOff className="h-3.5 w-3.5" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            {revealed ? "Hide" : "Reveal"}
          </Button>
          <Button variant="primary" onClick={copy}>
            <Copy className="h-3.5 w-3.5" />
            Copy
          </Button>
        </div>
      </div>
      <p className="border-t border-white/10 px-4 py-2.5 text-[11px] text-faint">
        Last used 4 minutes ago from mcp-client/1.4.2 · Created Jun 02, 2026
      </p>
    </Card>
  );
}
