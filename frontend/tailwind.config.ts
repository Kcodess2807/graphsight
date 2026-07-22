import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
        // memory layer — Space Grotesk display face (the category signature:
        // Supermemory uses it too) for wordmark, heroes, panel titles
        display: ["Space Grotesk", "Inter", "ui-sans-serif", "sans-serif"],
      },
      spacing: {
        "4.5": "1.125rem",
      },
      colors: {
        // memory layer — dual-theme tokens resolved by CSS vars set in
        // index.css (.m-light warm paper / .m-dark void). "line" is the
        // hairline+fill base (ink in light, white in dark); "neon" is the
        // electric synapse-blue accent.
        paper: "rgb(var(--m-paper) / <alpha-value>)",
        surface: "rgb(var(--m-surface) / <alpha-value>)",
        raised: "rgb(var(--m-raised) / <alpha-value>)",
        ink: {
          DEFAULT: "rgb(var(--m-ink) / <alpha-value>)",
          dim: "rgb(var(--m-ink-dim) / <alpha-value>)",
          ghost: "rgb(var(--m-ink-ghost) / <alpha-value>)",
        },
        line: "rgb(var(--m-line) / <alpha-value>)",
        neon: {
          DEFAULT: "rgb(var(--m-accent) / <alpha-value>)",
          purple: "rgb(var(--m-accent) / <alpha-value>)",
        },
        live: "#10B981",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgb(0 0 0 / 0.03), 0 1px 3px 0 rgb(0 0 0 / 0.05)",
        lifted:
          "0 4px 12px -2px rgb(0 0 0 / 0.08), 0 2px 6px -2px rgb(0 0 0 / 0.05)",
        node: "0 6px 20px -6px rgb(79 70 229 / 0.35), 0 2px 6px -2px rgb(0 0 0 / 0.08)",
        // memory layer — accent glow tiers for traced paths and pills
        glow: "0 0 0 1px rgb(var(--m-accent) / 0.4), 0 0 28px -6px rgb(var(--m-accent) / 0.4)",
        "glow-sm": "0 0 0 1px rgb(var(--m-accent) / 0.25), 0 0 14px -3px rgb(var(--m-accent) / 0.3)",
        "panel-dark":
          "0 0 0 1px rgb(var(--m-line) / 0.08), 0 16px 48px -12px rgb(0 0 0 / 0.45)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "dash-flow": {
          to: { strokeDashoffset: "-16" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "border-spin": {
          "100%": { transform: "rotate(360deg)" },
        },
        // memory layer — expanding sonar ring on nodes while the graph "searches"
        "trace-ping": {
          "0%": { transform: "scale(1)", opacity: "0.5" },
          "80%, 100%": { transform: "scale(1.9)", opacity: "0" },
        },
        // memory layer — vertical light sweep across the canvas during a query
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100vw)" },
        },
        // memory layer — soft breathing glow for citation pills
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 1px rgb(var(--m-accent) / 0.25), 0 0 10px -2px rgb(var(--m-accent) / 0.28)" },
          "50%": { boxShadow: "0 0 0 1px rgb(var(--m-accent) / 0.5), 0 0 18px -2px rgb(var(--m-accent) / 0.5)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "dash-flow": "dash-flow 0.6s linear infinite",
        shimmer: "shimmer 2s infinite",
        "fade-in-up": "fade-in-up 0.4s ease-out forwards",
        "border-spin": "border-spin 4s linear infinite",
        "trace-ping": "trace-ping 1.4s cubic-bezier(0, 0, 0.2, 1) infinite",
        scan: "scan 2.4s cubic-bezier(0.4, 0, 0.2, 1) infinite",
        "glow-pulse": "glow-pulse 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};

export default config;
