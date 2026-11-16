import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "./api";
import { addableQuantities, lineQuantities, MAX_PER_SELECT } from "./cart";

describe("addableQuantities", () => {
  it("ofrece de 1 al stock disponible", () => {
    expect(addableQuantities(3)).toEqual([1, 2, 3]);
  });
  it("descuenta lo que ya está en el carrito", () => {
    expect(addableQuantities(5, 3)).toEqual([1, 2]);
    expect(addableQuantities(5, 5)).toEqual([]);
    expect(addableQuantities(2, 7)).toEqual([]);
  });
  it("tiene un tope por selección", () => {
    expect(addableQuantities(40)).toHaveLength(MAX_PER_SELECT);
  });
  it("sin stock no ofrece nada", () => {
    expect(addableQuantities(0)).toEqual([]);
  });
});

describe("lineQuantities", () => {
  it("permite hasta el stock", () => {
    expect(lineQuantities(4, 1)).toEqual([1, 2, 3, 4]);
  });
  it("si el stock bajó, mantiene visible la cantidad actual", () => {
    expect(lineQuantities(1, 3)).toEqual([1, 2, 3]);
  });
});

describe("errorMessage", () => {
  it("usa el texto del backend", () => {
    expect(errorMessage(new ApiError(409, "Ya existe una cuenta con ese correo"))).toBe(
      "Ya existe una cuenta con ese correo",
    );
  });
  it("usa el mensaje de los errores de stock", () => {
    expect(errorMessage(new ApiError(409, { message: "Solo quedan 2 unidades", available: 2 }))).toBe(
      "Solo quedan 2 unidades",
    );
  });
  it("traduce los errores de validación por campo", () => {
    const detail = [{ loc: ["body", "password"], msg: "too short" }, { loc: ["body", "email"] }];
    expect(errorMessage(new ApiError(422, detail))).toContain("contraseña");
    expect(errorMessage(new ApiError(422, detail))).toContain("correo");
  });
  it("da un mensaje útil sin conexión o con error del servidor", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toContain("conectar");
    expect(errorMessage(new ApiError(503, null))).toContain("Inténtalo de nuevo");
  });
});
