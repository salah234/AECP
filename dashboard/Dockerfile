# syntax=docker/dockerfile:1.7

FROM node:22-slim AS deps
WORKDIR /app
COPY dashboard/package.json ./
RUN npm install

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY dashboard/ .
# Next.js inlines NEXT_PUBLIC_* vars into the client bundle at build time,
# not at container start — a plain runtime `environment:` entry in
# docker-compose.yml never reaches this step, so it must come in as a
# build ARG instead (docker-compose.yml passes it via `build.args`).
ARG NEXT_PUBLIC_GATEWAY_URL
ENV NEXT_PUBLIC_GATEWAY_URL=$NEXT_PUBLIC_GATEWAY_URL
RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app
RUN useradd --system --uid 10001 dashboard
COPY --from=builder --chown=dashboard:dashboard /app/.next/standalone ./
COPY --from=builder --chown=dashboard:dashboard /app/.next/static ./.next/static
COPY --from=builder --chown=dashboard:dashboard /app/public ./public
USER dashboard
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "server.js"]
