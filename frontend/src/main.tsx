/**
 * Punto de entrada del frontend.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { initAnalytics, initWebVitals } from "./analytics";
import App from "./App";
import "./styles/index.css";

// Analítica: GA4 se descarga en segundo plano; Web Vitals observa desde el inicio.
initAnalytics();
initWebVitals();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Datos del catálogo: se consideran frescos 30 s para no repetir peticiones al navegar.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
