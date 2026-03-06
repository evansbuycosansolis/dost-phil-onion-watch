import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef9f6",
          100: "#d5eee7",
          200: "#acddcf",
          300: "#7ec8b3",
          400: "#4ea894",
          500: "#2e8e7c",
          600: "#1f7165",
          700: "#195a52",
          800: "#164843",
          900: "#143e39"
        }
      }
    },
  },
  plugins: [],
};

export default config;
