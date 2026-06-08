/**
 * Bridges Clerk's React-only `getToken()` to the plain-function API layer.
 *
 * The functions in api.ts are module-level (not React components), so they can't
 * call the `useAuth()` hook directly. Instead, an in-tree component registers
 * Clerk's token getter here ONCE (see <AuthTokenBridge/> in App.tsx), and api.ts
 * pulls the current token from this module before each request.
 */

type TokenGetter = () => Promise<string | null>;

// The currently-registered getter. null when Clerk is disabled or not yet mounted.
let _getter: TokenGetter | null = null;

/** Register (or clear, with null) the Clerk token getter. Called from App.tsx. */
export function setTokenGetter(getter: TokenGetter | null): void {
  _getter = getter;
}

/**
 * Return a fresh Clerk session JWT, or null when unauthenticated / Clerk off.
 * Clerk's getToken() transparently refreshes the short-lived token as needed.
 * Any failure degrades to null so requests fall back to the unauthenticated
 * path (which the backend's dev-bypass mode still accepts locally).
 */
export async function getAuthToken(): Promise<string | null> {
  if (!_getter) return null;
  try {
    return await _getter();
  } catch {
    return null;
  }
}
