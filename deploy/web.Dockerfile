# Builds the UI against the API on the same origin, then serves it with Caddy.
FROM node:24-alpine AS build
WORKDIR /ui
RUN corepack enable
COPY ui/package.json ui/pnpm-lock.yaml ui/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY ui/ ./
ARG PUBLIC_URL
ENV VITE_BACKEND_MODE=api \
    VITE_API_URL=${PUBLIC_URL}
RUN test -n "$PUBLIC_URL" && pnpm exec vite build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /ui/dist /srv
