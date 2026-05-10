import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output bundles only what's needed for production runtime.
  // Required by apps/web/Dockerfile so the runtime stage stays small.
  output: "standalone",

  // Strict React mode catches common bugs in dev.
  reactStrictMode: true,

  // The api base URL is read at runtime from NEXT_PUBLIC_API_BASE
  // (set in docker-compose.yml). Falls back to localhost for `pnpm dev`.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  },

  // Future: server external packages (e.g. argon2 if/when SSR auth lands).
  serverExternalPackages: [],
};

export default nextConfig;
