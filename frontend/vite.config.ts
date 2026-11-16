/**
 * Configuración de Vite.
 * En desarrollo, /api y /media se reenvían al Nginx del Docker Compose
 * (http://localhost:8080), así el frontend usa la misma API que en producción.
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backend = process.env.VITE_DEV_BACKEND ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  // Las variables se leen del .env de la raíz del repositorio (el mismo que usa
  // Docker Compose). Vite solo entrega al navegador las que empiezan con VITE_,
  // así que secretos como JWT_SECRET nunca llegan al frontend.
  envDir: "..",
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      "/media": backend,
      "/health": backend,
    },
  },
  build: {
    target: "es2020",
    // Mapa de fuentes para depurar en el navegador sin afectar el peso de la página.
    sourcemap: true,
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
