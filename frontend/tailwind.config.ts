import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  // v3's hover: fires on touch and sticks after a tap
  future: { hoverOnlyWhenSupported: true },
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
        soft: "2px 3px 0 0 #131316",
        lifted: "3px 4px 0 0 #131316",
      },
      keyframes: {
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
      },
      animation: {
        "trace-ping": "trace-ping 1.4s cubic-bezier(0, 0, 0.2, 1) infinite",
        scan: "scan 2.4s cubic-bezier(0.4, 0, 0.2, 1) infinite",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
