# The web app (and the customer verify page) served by Caddy, which also forwards /api to the API.
# Built from the repo root (the rules in shared/ are part of the web build):
#   docker build -f infra/web.Dockerfile -t vayu-web .
FROM node:22-alpine AS build
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY shared /src/shared
COPY web ./
# Web Sentry: read at build time; empty = off (no source maps are made without an upload token)
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_ENV=production
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN VITE_SENTRY_ENV=$VITE_SENTRY_ENV
RUN npm run build && test -z "$(find dist -name '*.map')"

FROM caddy:2-alpine
COPY --from=build /src/web/dist /srv
COPY infra/Caddyfile /etc/caddy/Caddyfile
