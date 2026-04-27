FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY package.json pnpm-workspace.yaml ./
COPY apps/web-console/package.json ./apps/web-console/
RUN pnpm install --frozen-lockfile || pnpm install
COPY apps/web-console ./apps/web-console/
WORKDIR /app/apps/web-console
RUN pnpm build

FROM nginx:alpine
COPY --from=builder /app/apps/web-console/dist /usr/share/nginx/html
COPY apps/web-console/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
