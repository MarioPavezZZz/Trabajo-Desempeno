import { describe, expect, it } from "vitest";
import { formatCLP, formatChange, formatDate } from "./format";

describe("formatCLP", () => {
  it.each([
    [290, "$290"],
    [5390, "$5.390"],
    [164990, "$164.990"],
    [1234567, "$1.234.567"],
  ])("%i -> %s", (amount, expected) => {
    expect(formatCLP(amount)).toBe(expected);
  });
});

describe("formatChange", () => {
  it("usa signo, coma decimal y espacio antes del %", () => {
    expect(formatChange(72.2)).toBe("+72,2 %");
    expect(formatChange(-5)).toBe("−5,0 %");
    expect(formatChange(0)).toBe("0,0 %");
  });
});

describe("formatDate", () => {
  it("formatea fechas ISO en español de Chile sin desfase de zona horaria", () => {
    expect(formatDate("2024-11-08")).toMatch(/^8 nov\.? 2024$/);
    expect(formatDate(null)).toBe("");
  });
});
