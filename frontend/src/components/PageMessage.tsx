import { usePageTitle } from "@/lib/usePageTitle";

// full-page dead end (404, render crash): plain <a> so a crash gets a clean reload
export function PageMessage({ title, body }: { title: string; body: string }) {
  usePageTitle(title);
  return (
    <main
      tabIndex={-1}
      className="m-light flex min-h-dvh flex-col items-center justify-center bg-paper px-5 text-center font-sans antialiased outline-none"
    >
      <h1 className="font-display text-3xl font-bold tracking-tight text-[#131316]">{title}</h1>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-zinc-600">{body}</p>
      <p className="mt-6 flex gap-4 text-sm font-bold text-emerald-700">
        <a href="/" className="underline underline-offset-2">Go home</a>
        <a href="/memory/preview" className="underline underline-offset-2">Open the live demo</a>
      </p>
    </main>
  );
}
