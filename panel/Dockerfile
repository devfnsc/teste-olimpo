# Build do painel Next.js para produção (Render ou Docker local).
FROM node:22-alpine AS builder
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . ./
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=10000
RUN apk add --no-cache libc6-compat
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 10000
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 node server.js"]
