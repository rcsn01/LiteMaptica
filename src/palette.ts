import type { BlockState } from "./types";

const colors: Record<string, number> = {
  "minecraft:air": 0x000000,
  "minecraft:stone": 0x8b8b86,
  "minecraft:stone_bricks": 0x777873,
  "minecraft:oak_planks": 0xb58a55,
  "minecraft:dark_oak_planks": 0x4b321e,
  "minecraft:glass": 0xaad7d5,
  "minecraft:bricks": 0x9b4a3c,
  "minecraft:mossy_stone_bricks": 0x68705a,
};

export function blockColor(state: BlockState): number {
  if (colors[state.id] !== undefined) return colors[state.id];
  let hash = 2166136261;
  for (const character of state.id) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 8) & 0x7f7f7f) | 0x505050;
}

export function confidenceColor(occupancy: number, material: number): number {
  const value = Math.max(0, Math.min(1, Math.min(occupancy, material)));
  const red = Math.round(230 * (1 - value) + 74 * value);
  const green = Math.round(70 * (1 - value) + 205 * value);
  const blue = Math.round(66 * (1 - value) + 118 * value);
  return (red << 16) | (green << 8) | blue;
}

export function displayName(id: string): string {
  return id.replace("minecraft:", "").split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}
