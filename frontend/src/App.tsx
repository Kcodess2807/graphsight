import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ClerkProvider, useAuth } from "@clerk/clerk-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";
import { TraceDashboard } from "@/components/TraceDashboard";
import TraceRAGConceptsDoc from "@/components/docs/TraceRAGConceptsDoc";
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

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<TraceDashboard />} />
      <Route path="/docs/concepts" element={<TraceRAGConceptsDoc />} />
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
