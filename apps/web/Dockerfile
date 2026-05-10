# Multi-stage Next.js Dockerfile.
#
# Build context: ./apps/web (per docker-compose.yml `build: ./apps/web`).
# Replaces the M0.1 placeholder.
#
# Standalone output (`output: "standalone"` in next.config.ts) bundles
# only the runtime files, keeping the final image small.
#
# pnpm via corepack so the host doesn't need pnpm pre-installed for builds.

FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
ENV NEXT_TELEMETRY_DISABLED=1

# ---- deps ---------------------------------------------------------------
# Install only direct deps (no monorepo workspace links yet — apps/web
# is self-contained in M0.4; M0.6+ wires the shared-types workspace dep).
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --prefer-offline || pnpm install

# ---- builder ------------------------------------------------------------
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# ---- runtime ------------------------------------------------------------
FROM base AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN apk add --no-cache curl

# Standalone build outputs to .next/standalone with all node_modules
# inlined. Static assets and public/ are copied separately.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

# Healthcheck targets the disclaimer-gated root page; a 200 means the app
# is serving HTML. Phase 2 may add a lighter /api/healthz on the web tier.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
