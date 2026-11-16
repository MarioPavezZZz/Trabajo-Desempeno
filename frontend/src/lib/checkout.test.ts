import { describe, expect, it } from "vitest";
import { checkoutPayload, EMPTY_CHECKOUT, TEST_CHECKOUT, validateCheckout } from "./checkout";

describe("validateCheckout", () => {
  it("al invitado le exige nombre y correo", () => {
    const errors = validateCheckout(EMPTY_CHECKOUT, true);
    expect(Object.keys(errors).sort()).toEqual(["contact_email", "contact_name"]);
  });

  it("con cuenta no pide contacto", () => {
    expect(validateCheckout(EMPTY_CHECKOUT, false)).toEqual({});
  });

  it("envío a domicilio exige dirección completa", () => {
    const errors = validateCheckout({ ...EMPTY_CHECKOUT, shipping_method: "domicilio", phone: "123" }, false);
    expect(Object.keys(errors).sort()).toEqual(["comuna", "phone", "region", "street"]);
  });

  it("los datos de prueba son válidos", () => {
    expect(validateCheckout(TEST_CHECKOUT, true)).toEqual({});
  });
});

describe("checkoutPayload", () => {
  it("no envía dirección si es retiro ni contacto si hay cuenta", () => {
    const payload = checkoutPayload({ ...TEST_CHECKOUT, shipping_method: "retiro" }, false);
    expect(payload).toEqual({ shipping_method: "retiro" });
  });

  it("invitado con domicilio envía todo, sin espacios sobrantes", () => {
    const payload = checkoutPayload({ ...TEST_CHECKOUT, contact_name: "  Ana  " }, true);
    expect(payload.contact_name).toBe("Ana");
    expect(payload.street).toBe(TEST_CHECKOUT.street);
  });
});
