/**
 * Vuelve al inicio de la página al cambiar de ruta (en una SPA el navegador
 * conserva el scroll de la página anterior). Al volver atrás no interviene,
 * para que el listado recupere su posición.
 */
import { useEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

export default function ScrollToTop() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();
  useEffect(() => {
    if (navigationType !== "POP") window.scrollTo({ top: 0 });
  }, [pathname, navigationType]);
  return null;
}
