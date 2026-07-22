import { FadeIn } from "@/components/fade-in";
import { SettingsTabs } from "@/components/settings/settings-tabs";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <FadeIn>
        <h1 className="text-lg font-semibold tracking-tight text-white">
          Settings &amp; Billing
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          Plan, usage, and workspace configuration.
        </p>
      </FadeIn>

      <FadeIn delay={0.08}>
        <SettingsTabs />
      </FadeIn>
    </div>
  );
}
