/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base:    "#09090e",
          panel:   "#0f0f19",
          card:    "#13131e",
          surface: "#1a1a28",
          hover:   "#1e1e2e",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.07)",
          subtle:  "rgba(255,255,255,0.04)",
          strong:  "rgba(255,255,255,0.13)",
        },
        accent: {
          DEFAULT: "#6366f1",
          light:   "#818cf8",
          dark:    "#4f46e5",
          glow:    "rgba(99,102,241,0.25)",
        },
        muted: {
          DEFAULT: "#6b7280",
          foreground: "#9ca3af",
        },
      },
      boxShadow: {
        // 상단 하이라이트를 모든 카드 그림자에 내장
        card:     "0 1px 2px rgba(0,0,0,0.55), 0 4px 16px rgba(0,0,0,0.4), 0 20px 48px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.07)",
        elevated: "0 2px 4px rgba(0,0,0,0.55), 0 8px 28px rgba(0,0,0,0.5), 0 28px 56px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,255,255,0.09)",
        float:    "0 12px 40px rgba(0,0,0,0.55), 0 48px 80px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1)",
        glass:    "0 8px 32px rgba(0,0,0,0.45), 0 2px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08)",
        hover:    "0 4px 20px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.11), inset 0 1px 0 rgba(255,255,255,0.09)",
        accent:   "0 4px 24px rgba(99,102,241,0.22), 0 1px 4px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.07)",
        glow:     "0 0 20px rgba(99,102,241,0.4), 0 0 60px rgba(99,102,241,0.18)",
        "glow-sm": "0 0 0 1px rgba(99,102,241,0.3), 0 0 12px rgba(99,102,241,0.28)",
        "nav-active": "0 0 0 1px rgba(99,102,241,0.2), 0 2px 12px rgba(99,102,241,0.15)",
      },
      backgroundImage: {
        "glass":         "linear-gradient(160deg, rgba(255,255,255,0.055) 0%, rgba(255,255,255,0.015) 60%, rgba(255,255,255,0.005) 100%)",
        "glass-strong":  "linear-gradient(160deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 100%)",
        "accent-subtle": "linear-gradient(135deg, rgba(99,102,241,0.13) 0%, rgba(167,139,250,0.06) 100%)",
        "nav-active":    "linear-gradient(90deg, rgba(99,102,241,0.18) 0%, rgba(99,102,241,0.06) 60%, transparent 100%)",
        "stat-emerald":  "linear-gradient(135deg, rgba(16,185,129,0.14) 0%, rgba(16,185,129,0.04) 100%)",
        "stat-indigo":   "linear-gradient(135deg, rgba(99,102,241,0.14) 0%, rgba(99,102,241,0.04) 100%)",
        "stat-amber":    "linear-gradient(135deg, rgba(245,158,11,0.14) 0%, rgba(245,158,11,0.04) 100%)",
        "stat-zinc":     "linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.02) 100%)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(14px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateX(-10px)" },
          to:   { opacity: "1", transform: "translateX(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to:   { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        ripple: {
          "0%":   { transform: "scale(0)", opacity: "0.7" },
          "100%": { transform: "scale(1)", opacity: "0" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.45" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 12px rgba(99,102,241,0.25)" },
          "50%":      { boxShadow: "0 0 20px rgba(99,102,241,0.45)" },
        },
      },
      animation: {
        "fade-in":   "fade-in 0.28s ease-out",
        "fade-up":   "fade-up 0.32s cubic-bezier(0.16,1,0.3,1)",
        "slide-in":  "slide-in 0.25s cubic-bezier(0.16,1,0.3,1)",
        "scale-in":  "scale-in 0.22s cubic-bezier(0.16,1,0.3,1) both",
        shimmer:     "shimmer 2s linear infinite",
        pulse:       "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite",
        ripple:      "ripple 0.55s ease-out forwards",
        "glow-pulse": "glow-pulse 2.5s ease-in-out infinite",
      },
      backdropBlur: {
        xs: "2px",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
