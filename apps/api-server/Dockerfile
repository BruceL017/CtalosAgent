FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-workspace.yaml* ./
COPY apps/api-server/package.json ./apps/api-server/
COPY packages/shared-types/package.json ./packages/shared-types/
RUN pnpm install --frozen-lockfile || pnpm install
COPY packages/shared-types ./packages/shared-types/
COPY apps/api-server ./apps/api-server/
WORKDIR /app/apps/api-server
RUN pnpm build

FROM node:20-alpine
WORKDIR /app
RUN npm install -g pnpm
COPY --from=builder /app/apps/api-server/dist ./dist
COPY --from=builder /app/apps/api-server/package.json ./
COPY --from=builder /app/node_modules ./node_modules
ENV NODE_ENV=production
EXPOSE 3001
CMD ["node", "dist/index.js"]
