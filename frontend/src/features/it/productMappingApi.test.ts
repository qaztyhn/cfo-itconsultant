import { describe, expect, it } from "vitest";
import { candidateEvidence, validPositiveDecimal, validateGlobal, type NewGlobal } from "./productMappingApi";

const global: NewGlobal = {
  code: "G-000500", name: "Synthetic product", category: "Cement",
  base_unit: "bag", weight_kg: "25", volume_m3: "0.018",
  handling_group_code: "N3", base_units_per_prep_unit: "40", flags: [],
};
describe("US-PRD-02 AC3, US-PRD-04 AC4 — mapping validation", () => {
  it("requires strictly positive, finite conversion values", () => {
    for (const value of ["0", "-1", "NaN", "", "Infinity", "1e400"]) {
      expect(validPositiveDecimal(value)).toBe(false);
    }
    expect(validPositiveDecimal("40")).toBe(true);
    expect(validPositiveDecimal("0.5")).toBe(true);
  });
  it("validates global-product required fields and N6/FRAGILE restriction", () => {
    expect(validateGlobal(global)).toEqual([]);
    expect(validateGlobal({ ...global, handling_group_code: "N6", flags: ["FRAGILE"] }))
      .toContain("N6 may not carry the FRAGILE flag.");
    expect(validateGlobal({ ...global, weight_kg: "0", base_units_per_prep_unit: "" }).join(" "))
      .toMatch(/Positive weight|base-units/);
    expect(validateGlobal({ ...global, code: "", base_unit: "" }).join(" ")).toMatch(/required/);
  });
  it("labels candidate evidence as rule-based, not AI confidence", () => {
    expect(candidateEvidence({ global_product_id: 1, code: "G1", name: "P1", reason: "gtin", score: 1 })).toBe("GTIN match");
    expect(candidateEvidence({ global_product_id: 2, code: "G2", name: "P2", reason: "name_sim", score: 0.6 }))
      .toContain("pg_trgm");
  });
});
