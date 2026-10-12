# syntax=docker/dockerfile:1
# Agent Observatory frontend — multi-stage build producing a Next.js
# standalone server that runs as a non-root user.

# Exact Node version + Alpine release, pinned by multi-arch index digest.
# node v22.23.3 released 2026-09-23 (before the 2026-09-25 dependency cutoff).
ARG NODE_IMAGE=node:22.23.3-alpine3.24@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The runtime only needs `node`: drop the package managers shipped in the
# base image, and create the unprivileged runtime user.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
        /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-* \
    && addgroup -S -g 1001 app && adduser -S -u 1001 -G app app
# Application files stay root-owned (read-only for the app user) so the
# process cannot rewrite server.js or the bundle. Only Next's runtime cache
# directory (ISR / image optimisation) is writable by the app user.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
RUN mkdir -p .next/cache && chown app:app .next/cache
USER app:app
EXPOSE 3000
CMD ["node", "server.js"]
