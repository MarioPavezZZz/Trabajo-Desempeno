/**
 * Fija el título de la pestaña y envía `page_view` a GA4.
 *
 * Se envía al cambiar de ruta o de título, no al cambiar filtros del listado
 * (que solo modifican la URL): así "páginas por sesión" refleja navegación real.
 * Con `title = null` (datos aún cargando) espera a tener el título definitivo.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { trackPageView } from "./events";

export function usePageView(title: string | null): void {
  const { pathname } = useLocation();
  useEffect(() => {
    if (!title) return;
    document.title = title;
    trackPageView(window.location.pathname + window.location.search, title);
  }, [pathname, title]);
}
