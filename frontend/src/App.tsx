import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ClerkProvider, useAuth } from "@clerk/clerk-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";
import { TraceDashboard } from "@/components/TraceDashboard";
import { LandingPage } from "@/components/landing/LandingPage";
import { MemoryImport } from "@/components/memory/MemoryImport";
import { MemoryPreview } from "@/components/memory/MemoryPreview";
import { MemoryStudio } from "@/components/memory/MemoryStudio";
import GraphsightConceptsDoc from "@/components/docs/GraphsightConceptsDoc";
import { SignInPage } from "@/components/auth/SignInPage";
import { SignUpPage } from "@/components/auth/SignUpPage";
import {
  CLERK_PUBLISHABLE_KEY,
  clerkEnabled,
  clerkAppearance,
} from "@/lib/clerk";
import { setTokenGetter } from "@/lib/authToken";

/**
 * Registers Clerk's getToken() with the API layer so plain-function fetches in
 * api.ts can attach a Bearer token. Renders nothing; must live INSIDE
 * <ClerkProvider> because it relies on the useAuth() hook.
 */
function AuthTokenBridge() {
  const { getToken } = useAuth();
  useEffect(() => {
    // Clerk's getToken() returns the current session JWT (auto-refreshed).
    setTokenGetter(() => getToken());
    return () => setTokenGetter(null); // clear on unmount to avoid a stale getter
  }, [getToken]);
  return null;
}

// the live Studio needs the backend; deployed static builds hide it so
// visitors never hit a broken page. dev builds (or the flag) show it.
const SHOW_STUDIO =
  import.meta.env.DEV || import.meta.env.VITE_ENABLE_STUDIO === "1";

function AppRoutes() {
  return (
    <Routes>
      {/* root: the landing page — pip packages + hosted engine pitch */}
      <Route path="/" element={<LandingPage />} />
      {/* mock data with simulated tracing, no backend needed */}
      <Route path="/memory/preview" element={<MemoryPreview />} />
      {/* render an external trace (graphsight-langgraph) — drop/paste JSON */}
      <Route path="/memory/import" element={<MemoryImport />} />
      <Route path="/docs/concepts" element={<GraphsightConceptsDoc />} />
      {SHOW_STUDIO && (
        <>
          {/* the live studio: backend-wired, sample fallback */}
          <Route path="/studio" element={<MemoryStudio />} />
          <Route path="/memory" element={<MemoryStudio />} />
          {/* previous dashboard, kept for reference */}
          <Route path="/classic" element={<TraceDashboard />} />
        </>
      )}
      {clerkEnabled && (
        <>
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
        </>
      )}
    </Routes>
  );
}

export default function App() {
  // Clerk is optional: with no publishable key the app runs un-authed so the
  // dashboard never hard-crashes before a key is configured.
  const routed = (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );

  return (
    <TooltipProvider delayDuration={150} skipDelayDuration={300}>
      {clerkEnabled ? (
        <ClerkProvider
          publishableKey={CLERK_PUBLISHABLE_KEY!}
          appearance={clerkAppearance}
          afterSignOutUrl="/"
        >
          <AuthTokenBridge />
          {routed}
        </ClerkProvider>
      ) : (
        routed
      )}
      <Toaster
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast:
              "!rounded-xl !border-border !bg-white !text-zinc-900 !shadow-lifted !font-sans",
            description: "!text-zinc-500",
          },
        }}
      />
    </TooltipProvider>
  );
}
