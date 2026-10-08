import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@researchly/contract": path.resolve(import.meta.dirname, "../../packages/contract/src/index.ts"),
      "client-only": path.resolve(import.meta.dirname, "tests/unit/stubs/empty.ts"),
      "@": path.resolve(import.meta.dirname, "."),
    },
  },
  // Component tests (.test.tsx) render to static markup with react-dom/server; no DOM is needed.
  // JSX follows tsconfig's "react-jsx".
  test: {
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    environment: "node",
  },
});
