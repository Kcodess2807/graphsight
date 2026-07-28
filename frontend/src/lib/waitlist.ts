// Waitlist signup. Endpoint-agnostic: any service that accepts a JSON POST
// with { email } works — Formspree, Loops, Tally webhook, or your own route.
// Set VITE_WAITLIST_ENDPOINT to switch providers without touching this file.

const ENDPOINT = import.meta.env.VITE_WAITLIST_ENDPOINT as string | undefined;

// shown as a mailto when no endpoint is configured; unset = no fallback offered
export const FALLBACK_EMAIL = import.meta.env.VITE_CONTACT_EMAIL as string | undefined;

export const isWaitlistConfigured = (): boolean => Boolean(ENDPOINT);

export class WaitlistError extends Error {
  // true when the signup can't work at all, so the UI offers the mailto instead
  readonly unconfigured: boolean;

  constructor(message: string, unconfigured = false) {
    super(message);
    this.name = "WaitlistError";
    this.unconfigured = unconfigured;
  }
}

/** POST an email to the configured provider. Throws WaitlistError on failure. */
export async function joinWaitlist(
  email: string,
  source: string,
  signal?: AbortSignal
): Promise<void> {
  if (!ENDPOINT) {
    // Never report success we can't deliver — silently dropping the address is
    // the exact bug this replaced.
    throw new WaitlistError("Signup isn't connected yet.", true);
  }

  let res: Response;
  try {
    res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, source }),
      signal,
    });
  } catch {
    throw new WaitlistError("Couldn't reach the server. Check your connection and retry.");
  }

  // Formspree and Loops both answer 2xx with JSON, but some 2xx bodies still
  // report failure in the payload — check both.
  const body = await res.json().catch(() => null as unknown);
  const payload = (body ?? {}) as Record<string, unknown>;

  if (!res.ok) {
    throw new WaitlistError(providerMessage(payload) ?? `Signup failed (${res.status}).`);
  }
  if (payload.success === false) {
    throw new WaitlistError(providerMessage(payload) ?? "Signup failed. Try again.");
  }
}

/** Pull a human-readable reason out of a provider's error body, if there is one. */
function providerMessage(payload: Record<string, unknown>): string | null {
  if (typeof payload.message === "string" && payload.message) return payload.message;
  const errors = payload.errors;
  if (Array.isArray(errors) && errors.length) {
    const first = errors[0] as Record<string, unknown>;
    if (typeof first?.message === "string") return first.message;
  }
  return null;
}
