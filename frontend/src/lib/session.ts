/**
 * Estado compartido de sesión y carrito (React Query).
 *
 * El usuario y el carrito viven en el servidor; aquí solo se cachean y se
 * invalidan después de cada cambio, así el contador del encabezado y la
 * página del carrito siempre muestran lo mismo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Cart, User } from "./types";

export const ME_KEY = ["me"] as const;
export const CART_KEY = ["cart"] as const;

/** Usuario conectado, o `null` si no hay sesión (un 401 no es un error aquí). */
export function useMe() {
  return useQuery<User | null>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 5 * 60_000,
  });
}

export function useCart() {
  return useQuery<Cart>({ queryKey: CART_KEY, queryFn: api.cart, staleTime: 0 });
}

/** Mutaciones del carrito: cada una deja en caché el carrito que responde el servidor. */
export function useCartActions() {
  const qc = useQueryClient();
  const onSuccess = (cart: Cart) => qc.setQueryData(CART_KEY, cart);
  return {
    add: useMutation({
      mutationFn: ({ productId, quantity }: { productId: number; quantity: number }) =>
        api.addToCart(productId, quantity),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: ({ itemId, quantity }: { itemId: number; quantity: number }) =>
        api.updateCartItem(itemId, quantity),
      onSuccess,
      // Si falló por stock, se recarga el carrito para mostrar las cantidades reales.
      onError: () => qc.invalidateQueries({ queryKey: CART_KEY }),
    }),
    remove: useMutation({ mutationFn: (itemId: number) => api.removeCartItem(itemId), onSuccess }),
  };
}

/** Acciones de cuenta: al entrar o salir, se recargan usuario y carrito. */
export function useAuthActions() {
  const qc = useQueryClient();
  const refresh = async (user: User | null) => {
    qc.setQueryData(ME_KEY, user);
    await qc.invalidateQueries({ queryKey: CART_KEY });
  };
  return {
    login: useMutation({ mutationFn: api.login, onSuccess: refresh }),
    register: useMutation({ mutationFn: api.register, onSuccess: refresh }),
    logout: useMutation({ mutationFn: api.logout, onSuccess: () => refresh(null) }),
  };
}
