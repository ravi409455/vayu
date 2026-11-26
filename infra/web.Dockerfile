# syntax=docker/dockerfile:1
# The web app (and the customer verify page) served by Caddy, which also forwards /api to the API.
# Built from the repo root (the rules in shared/ are part of the web build):
#   docker build -f infra/web.Dockerfile -t vayu-web .
FROM node:26-alpine AS build
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY shared /src/shared
COPY web ./
# Web Sentry: read at build time; empty = off. One image for staging and production: the label
# (staging / production) comes from the address the page is opened on.
ARG VITE_SENTRY_DSN=""
# the commit id: Sentry groups errors by release; with the build secret sentry_token the source maps
# go to Sentry under that release and are deleted, so they are never served
ARG VITE_RELEASE=""
ARG SENTRY_ORG=""
ARG SENTRY_PROJECT=vayu-web
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN VITE_RELEASE=$VITE_RELEASE SENTRY_ORG=$SENTRY_ORG SENTRY_PROJECT=$SENTRY_PROJECT
RUN --mount=type=secret,id=sentry_token,env=SENTRY_AUTH_TOKEN npm run build && test -z "$(find dist -name '*.map')"

FROM caddy:2-alpine
COPY --from=build /src/web/dist /srv
COPY infra/Caddyfile /etc/caddy/Caddyfile
