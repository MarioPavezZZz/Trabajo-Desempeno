/**
 * Reglas de cantidad del carrito usadas por la interfaz.
 * El servidor valida lo mismo; esto solo evita ofrecer opciones imposibles.
 */

/** Máximo que se puede elegir de una vez en el selector de cantidad. */
export const MAX_PER_SELECT = 10;

/**
 * Cantidades que se pueden agregar: de 1 hasta lo que queda de stock
 * (descontando lo que ya está en el carrito), con tope de MAX_PER_SELECT.
 */
export function addableQuantities(stock: number, alreadyInCart = 0): number[] {
  const max = Math.min(Math.max(stock - alreadyInCart, 0), MAX_PER_SELECT);
  return Array.from({ length: max }, (_, i) => i + 1);
}

/** Cantidades para una línea del carrito: de 1 hasta el stock (al menos la actual). */
export function lineQuantities(stock: number, current: number): number[] {
  const max = Math.max(Math.min(stock, 99), current, 1);
  return Array.from({ length: max }, (_, i) => i + 1);
}
