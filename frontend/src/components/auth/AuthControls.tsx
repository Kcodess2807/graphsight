import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/clerk-react";
import { clerkEnabled, clerkAppearance } from "@/lib/clerk";
import { Button } from "@/components/ui/button";

/**
 * Header auth controls. Renders Sign in / Sign up when signed out, and the
 * UserButton (account menu + sign out) when signed in. Returns null when Clerk
 * isn't configured, so the header stays clean before a key is set.
 */
export function AuthControls() {
  if (!clerkEnabled) return null;

  return (
    <div className="flex items-center gap-2">
      <SignedOut>
        <SignInButton mode="modal">
          <Button variant="ghost" size="sm" className="text-zinc-600">
            Sign in
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button size="sm">Sign up</Button>
        </SignUpButton>
      </SignedOut>
      <SignedIn>
        <UserButton
          appearance={clerkAppearance}
          userProfileProps={{ appearance: clerkAppearance }}
        />
      </SignedIn>
    </div>
  );
}
