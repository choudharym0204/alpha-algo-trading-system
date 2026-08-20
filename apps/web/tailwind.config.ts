import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Terminal palette: dark, information-dense, but readable.
        surface: {
          DEFAULT: "#0b0f17",
          raised: "#111827",
          border: "#1f2937",
        },
        accent: {
          DEFAULT: "#22c55e",
          dim: "#166534",
        },
        buy: "#22c55e",
        sell: "#ef4444",
        warn: "#f59e0b",
        info: "#38bdf8",
        muted: "#9ca3af",
      },
    },
  },
  plugins: [],
};

export default config;
