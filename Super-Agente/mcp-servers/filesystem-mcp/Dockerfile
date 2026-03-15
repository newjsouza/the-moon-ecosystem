ARG NODE_VERSION=22-bookworm-slim

# ------------------------------
# Base
# ------------------------------
FROM node:${NODE_VERSION} AS base
WORKDIR /app

# ------------------------------
# Dependencies
# ------------------------------
FROM base AS deps
RUN --mount=type=cache,target=/root/.npm,sharing=locked,id=npm-cache \
    --mount=type=bind,source=packages/filesystem-mcp/package.json,target=packages/filesystem-mcp/package.json \
    --mount=type=bind,source=packages/filesystem-mcp/package-lock.json,target=packages/filesystem-mcp/package-lock.json \
    npm ci --omit=dev

# ------------------------------
# Builder
# ------------------------------
FROM base AS builder
RUN --mount=type=cache,target=/root/.npm,sharing=locked,id=npm-cache \
    --mount=type=bind,source=packages/filesystem-mcp/package.json,target=packages/filesystem-mcp/package.json \
    --mount=type=bind,source=packages/filesystem-mcp/package-lock.json,target=packages/filesystem-mcp/package-lock.json \
    npm ci
COPY packages/filesystem-mcp/src ./src
RUN npx tsc && shx chmod +x dist/src/*.js

# ------------------------------
# Runtime
# ------------------------------
FROM base
ENV NODE_ENV=production
USER node
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
ENTRYPOINT ["node", "dist/src/index.js"]