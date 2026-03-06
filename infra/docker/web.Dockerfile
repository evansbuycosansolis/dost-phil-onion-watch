FROM node:22-bullseye

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/types/package.json packages/types/package.json
COPY packages/domain/package.json packages/domain/package.json
COPY packages/config/package.json packages/config/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/ai-prompts/package.json packages/ai-prompts/package.json

RUN pnpm install --frozen-lockfile=false

COPY . .

WORKDIR /workspace/apps/web

EXPOSE 3000

CMD ["pnpm", "dev"]
