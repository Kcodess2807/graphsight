import { SignIn } from "@clerk/clerk-react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Wordmark } from "@/components/Wordmark";
import { clerkAppearance } from "@/lib/clerk";
import { usePageTitle } from "@/lib/usePageTitle";

export function SignInPage() {
  usePageTitle("Sign in");
  return (
    <div className="flex min-h-[100dvh] flex-col bg-zinc-50">
      <header className="flex items-center justify-between border-b border-border bg-white/70 px-6 py-3 backdrop-blur">
        <Link
          to="/"
          className="flex items-center gap-1.5 text-sm font-medium text-zinc-500 transition-colors hover:text-zinc-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
        <Wordmark />
      </header>

      <main tabIndex={-1} className="flex flex-1 outline-none items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
              Welcome back
            </h1>
            <p className="mt-1 text-sm text-zinc-500">
              Sign in to your Graphsight Studio workspace.
            </p>
          </div>
          <SignIn
            routing="path"
            path="/sign-in"
            signUpUrl="/sign-up"
            fallbackRedirectUrl="/"
            appearance={clerkAppearance}
          />
        </div>
      </main>
    </div>
  );
}
