FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig*.json vite.config.ts ./
COPY src ./src

ARG VITE_ENABLED_LLM_PROVIDERS=qwen,claude
ENV VITE_ENABLED_LLM_PROVIDERS=${VITE_ENABLED_LLM_PROVIDERS}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

ENV API_UPSTREAM=api:8000 \
    NGINX_ENVSUBST_FILTER=^API_UPSTREAM$

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
