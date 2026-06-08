import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/clerk-react";
import { clerkEnabled, clerkAppearance } from "@/lib/clerk";
import { Button } from "@/components/ui/button";

// header auth controls; null when clerk isn't configured
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
