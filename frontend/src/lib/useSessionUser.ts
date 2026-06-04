import { useUser } from "@clerk/clerk-react";
import { clerkEnabled } from "./clerk";

export interface SessionUser {
  userId: string | null;
  email: string | null;
  /** True once Clerk has resolved (or immediately when auth is disabled). */
  ready: boolean;
}

/**
 * Clerk's `useUser` may only be called inside a mounted `<ClerkProvider>`.
 * `clerkEnabled` is a build-time constant — when it's false the provider is
 * never mounted, so we must NOT call the hook. Because the constant never
 * changes between renders, this conditional call is hook-rules-safe.
 */
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
