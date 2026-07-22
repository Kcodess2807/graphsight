import React from "react";
import ReactDOM from "react-dom/client";
import * as Sentry from "@sentry/react";
import App from "./App";
import "./index.css";

// Sentry browser error + performance monitoring. No-op unless VITE_SENTRY_DSN is
// set, so local dev is unaffected. browserTracing captures render/layout timing
// (useful around the React Flow canvas); profiling traces the component tree.
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration()],
    // 1.0 traces everything (dev); scale down via the env var in production.
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 1.0),
  });
}

// withProfiler wraps the root so Sentry can trace mount/render performance.
const ProfiledApp = Sentry.withProfiler(App);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ProfiledApp />
  </React.StrictMode>
);
