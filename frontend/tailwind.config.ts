import type { Config } from "tailwindcss";

// Figment design tokens — figurelabs.ai-inspired light-blue SaaS palette + Inter.
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#f5f8ff", // light-blue tinted background
        panel: "#ffffff",
        surface2: "#eef3fc", // cool panel
        ink: "#0f1b35", // dark navy
        "ink-soft": "#3a4a6b",
        muted: "#7488a8",
        line: "#e2e9f5",
        "line-strong": "#cdd9ee",
        accent: "#3b82f6", // blue
        "accent-ink": "#1e40af", // dark blue (buttons/active)
        "accent-soft": "#eff6ff",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Apple SD Gothic Neo",
          "Noto Sans KR",
          "sans-serif",
        ],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(30,55,120,0.05), 0 1px 3px rgba(30,55,120,0.08)",
        soft: "0 4px 24px rgba(30,55,120,0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
