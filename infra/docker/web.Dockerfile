FROM node:22-bullseye

WORKDIR /workspace

RUN corepack enable

COPY . .

RUN pnpm install --frozen-lockfile=false

RUN pnpm --filter @phil-onion-watch/web exec next build

WORKDIR /workspace/apps/web

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
