import { describe, expect, it } from "vitest";
import { maskEmail, maskPhone } from "./mask";

describe("maskEmail (03 mục 4)", () => {
  it("keeps the first character and the domain", () => {
    expect(maskEmail("user@takservice.demo")).toBe("u•••@takservice.demo");
  });

  it("does not leak the local part length", () => {
    expect(maskEmail("a@x.se")).toBe("a•••@x.se");
    expect(maskEmail("averylonglocalpart@x.se")).toBe("a•••@x.se");
  });

  it("masks completely when the address is malformed", () => {
    expect(maskEmail("not-an-email")).toBe("•••");
    expect(maskEmail("@x.se")).toBe("•••");
  });
});

describe("maskPhone (03 mục 4)", () => {
  it.each(["+46 70 123 12 34", "+46701231234", "+46-70-123-12-34"])("masks %s as the spec example", (input) => {
    expect(maskPhone(input)).toBe("+46 •• ••• 12 34");
  });

  it("masks a national number without a country code", () => {
    expect(maskPhone("070 123 12 34")).toBe("•• ••• 12 34");
  });

  it("never exposes more than the last four digits", () => {
    expect(maskPhone("+46 70 123 99 87")).not.toMatch(/70|123/);
  });

  it("masks a too-short value completely", () => {
    expect(maskPhone("123")).toBe("•• •••");
  });
});