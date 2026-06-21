import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#1a1a2e",
          raised: "#16213e",
          overlay: "#0f3460",
        },
        accent: {
          DEFAULT: "#e94560",
          muted: "#c73652",
        },
      },
    },
  },
  plugins: [],
};

export default config;
