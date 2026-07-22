import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        muted: "#888888",
        faint: "#555555",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // slow border shimmer for the "connect" card
        glow: {
          "0%, 100%": { boxShadow: "0 0 0 1px rgba(255,255,255,0.10), 0 0 24px -8px rgba(255,255,255,0.10)" },
          "50%": { boxShadow: "0 0 0 1px rgba(255,255,255,0.18), 0 0 32px -6px rgba(255,255,255,0.16)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.4s ease-out both",
        glow: "glow 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
