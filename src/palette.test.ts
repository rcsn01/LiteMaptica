import { describe, expect, it } from "vitest";
import { blockColor, confidenceColor, displayName } from "./palette";

describe("viewer palette", () => {
  it("maps known block states deterministically", () => expect(blockColor({ id: "minecraft:stone", properties: {} })).toBe(0x8b8b86));
  it("maps confidence endpoints", () => { expect(confidenceColor(0, 0)).toBe(0xe64642); expect(confidenceColor(1, 1)).toBe(0x4acd76); });
  it("formats identifiers", () => expect(displayName("minecraft:mossy_stone_bricks")).toBe("Mossy Stone Bricks"));
});
