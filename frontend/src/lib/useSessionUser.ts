import { useUser } from "@clerk/clerk-react";
import { clerkEnabled } from "./clerk";

export interface SessionUser {
  userId: string | null;
  email: string | null;
  ready: boolean;
}

// clerkEnabled is a build-time constant, so the conditional useUser call is hook-rules-safe
export function useSessionUser(): SessionUser {
  if (!clerkEnabled) {
    return { userId: null, email: null, ready: true };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { user, isLoaded } = useUser();
  return {
    userId: user?.id ?? null,
    email: user?.primaryEmailAddress?.emailAddress ?? null,
    ready: isLoaded,
  };
}
