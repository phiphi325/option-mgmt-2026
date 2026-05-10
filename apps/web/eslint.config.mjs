// Flat-config ESLint setup for Next.js 16.2.6.
//
// `eslint-config-next` 16.x exports a native flat-config array via its
// `core-web-vitals` entry point. Spread it directly — no FlatCompat shim.

import next from "eslint-config-next/core-web-vitals";

const config = [
  ...next,
  {
    ignores: [".next/**", "node_modules/**", "dist/**", "out/**", "coverage/**"],
  },
];

export default config;
