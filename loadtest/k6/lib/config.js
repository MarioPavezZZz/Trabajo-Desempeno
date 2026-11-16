/**
 * Configuración de las pruebas de carga: perfiles, pesos de cada
 * comportamiento y parámetros que se pueden cambiar por variable de entorno.
 *
 * Variables (todas opcionales):
 *   BASE_URL   URL del sitio (por defecto el Docker Compose local).
 *   PERFIL     humo | baja | normal | pico | estres
 *   RATE       sesiones nuevas por segundo en la meseta (reemplaza la del perfil).
 *   DURATION   duración de la meseta, p. ej. "10m" (reemplaza la del perfil).
 *   RAMP       duración del ramp-up, p. ej. "1m".
 *   MAX_VUS    máximo de usuarios virtuales simultáneos.
 *   THINK      multiplicador de las pausas entre acciones (1 = realista, 0 = sin pausas).
 *   ASSETS     true | false: descargar también imágenes (como un navegador).
 *
 * Modelo de carga ABIERTO (ramping-arrival-rate): llegan N sesiones por
 * unidad de tiempo aunque las anteriores no hayan terminado, como en un sitio
 * real. Así, cuando el servidor se satura, la cola crece y se ve el punto de
 * quiebre (un modelo cerrado ocultaría la saturación al frenar a los usuarios).
 */

export const BASE_URL = (__ENV.BASE_URL || "http://host.docker.internal:8080").replace(/\/+$/, "");
export const PERFIL = __ENV.PERFIL || "humo";
export const THINK = __ENV.THINK !== undefined ? Number(__ENV.THINK) : 1;
export const WITH_ASSETS = (__ENV.ASSETS || "true") === "true";

/** Correo de los usuarios que crea k6 (el script de reinicio los reconoce por este patrón). */
export function loadtestEmail() {
  return `carga-k6-${__VU}-${__ITER}-${Date.now() % 1000000}@example.com`;
}
export const LOADTEST_PASSWORD = "clave-de-carga-k6";

/**
 * Proporción de cada comportamiento sobre el total de sesiones.
 * Inspirada en embudos típicos de e-commerce: la mayoría navega, pocos compran.
 */
export const WEIGHTS = {
  navegante: 0.45,
  buscador: 0.25,
  abandono: 0.15,
  comprador_invitado: 0.1,
  comprador_cuenta: 0.05,
};

/**
 * Perfiles. `stages` está en SESIONES POR MINUTO del total (se reparte por peso).
 * `plateau` marca la etapa cuya tasa/duración se puede reemplazar con RATE/DURATION.
 */
export const PROFILES = {
  humo: { kind: "smoke" },
  baja: {
    maxVUs: 150,
    stages: [
      { duration: "1m", target: 60, ramp: true },
      { duration: "4m", target: 60, plateau: true },
    ],
  },
  normal: {
    maxVUs: 600,
    stages: [
      { duration: "2m", target: 300, ramp: true },
      { duration: "13m", target: 300, plateau: true },
    ],
  },
  pico: {
    maxVUs: 2000,
    stages: [
      { duration: "1m", target: 60, ramp: true },
      { duration: "30s", target: 1200 },
      { duration: "2m", target: 1200, plateau: true },
      { duration: "30s", target: 60 },
      { duration: "1m", target: 60 },
    ],
  },
  estres: {
    maxVUs: 4000,
    stages: [
      { duration: "30s", target: 300, ramp: true },
      { duration: "2m", target: 300 },
      { duration: "30s", target: 600 },
      { duration: "2m", target: 600 },
      { duration: "30s", target: 1200 },
      { duration: "2m", target: 1200 },
      { duration: "30s", target: 2400 },
      { duration: "2m", target: 2400 },
      { duration: "30s", target: 4800 },
      { duration: "2m", target: 4800, plateau: true },
    ],
  },
};

/** Etapas del perfil con los reemplazos de RATE / DURATION / RAMP aplicados. */
export function profileStages(profile) {
  const rate = __ENV.RATE ? Number(__ENV.RATE) * 60 : null; // sesiones/s -> por minuto
  return profile.stages.map((s) => ({
    duration: (s.plateau && __ENV.DURATION) || (s.ramp && __ENV.RAMP) || s.duration,
    target: rate !== null && (s.plateau || s.ramp) ? rate : s.target,
  }));
}

export function maxVUs(profile) {
  return __ENV.MAX_VUS ? Number(__ENV.MAX_VUS) : profile.maxVUs;
}
