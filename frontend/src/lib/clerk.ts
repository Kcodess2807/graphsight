/**
 * Clerk publishable key (pk_test_… / pk_live_…). Optional: when it's absent the
 * app runs without auth — the dashboard still works and the auth UI is hidden —
 * so the project never hard-crashes before a key is configured.
 */
export const CLERK_PUBLISHABLE_KEY = import.meta.env
  .VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

export const clerkEnabled = Boolean(CLERK_PUBLISHABLE_KEY);

/**
 * Shared Clerk appearance, themed to match Graphsight Studio:
 *   - colorPrimary = the app's indigo primary (#4F46E5)
 *   - flat: no heavy card shadow, a single hairline border, rounded-xl corners
 *
 * Typed structurally where it's consumed (ClerkProvider / SignIn `appearance`).
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "#4F46E5", // indigo-600 — the Tailwind --primary
    colorText: "#18181b", // zinc-900
    colorTextSecondary: "#71717a", // zinc-500
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    colorInputText: "#18181b",
    borderRadius: "0.75rem", // rounded-xl
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  elements: {
    // Flat, minimal: kill the default drop shadow, use one hairline border.
    card: "shadow-none border border-zinc-200 rounded-xl",
    rootBox: "w-full",
    headerTitle: "text-zinc-900 font-semibold tracking-tight",
    headerSubtitle: "text-zinc-500",
    socialButtonsBlockButton:
      "border border-zinc-200 shadow-none hover:bg-zinc-50 rounded-lg",
    formButtonPrimary:
      "bg-indigo-600 hover:bg-indigo-700 shadow-none normal-case font-medium rounded-lg",
    formFieldInput:
      "border border-zinc-200 shadow-none rounded-lg focus:ring-2 focus:ring-indigo-500/30",
    footerActionLink: "text-indigo-600 hover:text-indigo-700",
    badge: "bg-indigo-50 text-indigo-700",
    // UserButton dropdown
    userButtonPopoverCard: "shadow-lifted border border-zinc-200 rounded-xl",
    avatarBox: "rounded-lg",
  },
};
