// Flat-config ESLint setup for Next.js 16.2.6.
// eslint-config-next exposes a flat-config-compatible default export under
// `eslint-config-next/flat`. Falls back to `next/core-web-vitals` rules.

import next from "eslint-config-next";

export default [
  ...next,
  {
    ignores: [".next/**", "node_modules/**", "dist/**", "out/**"],
  },
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
];
