# Imagen del sitio público: compila el frontend y lo sirve con Nginx, que además
# hace de proxy hacia la API y sirve las imágenes del catálogo.
# Contexto de build: raíz del repositorio (necesita frontend/ e infra/nginx/).

# ---- Etapa 1: compilación ----
FROM node:22.12-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Variables públicas del frontend (se fijan en tiempo de compilación).
ARG VITE_GA4_MEASUREMENT_ID=""
ARG VITE_TRAFFIC_TYPE="real"
ARG VITE_TEST_HELPERS="false"
ARG VITE_ANALYTICS_DEBUG="false"
ENV VITE_GA4_MEASUREMENT_ID=$VITE_GA4_MEASUREMENT_ID \
    VITE_TRAFFIC_TYPE=$VITE_TRAFFIC_TYPE \
    VITE_TEST_HELPERS=$VITE_TEST_HELPERS \
    VITE_ANALYTICS_DEBUG=$VITE_ANALYTICS_DEBUG
RUN npm run build

# ---- Etapa 2: servidor ----
FROM nginx:1.27.3-alpine
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /src/dist /usr/share/nginx/html
