import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Document text must only ever be rendered as text (never as HTML).
      "react/no-danger": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[property.name='innerHTML']",
          message: "Never write HTML from data; render text nodes instead.",
        },
        {
          selector: "MemberExpression[property.name='outerHTML']",
          message: "Never write HTML from data; render text nodes instead.",
        },
        {
          selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
          message: "Never write HTML from data; render text nodes instead.",
        },
      ],
    },
  },
  globalIgnores([".next/**", ".next-*/**", "node_modules/**", "test-results/**", "playwright-report/**", "next-env.d.ts"]),
]);
