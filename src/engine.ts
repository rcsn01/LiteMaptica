import { invoke } from "@tauri-apps/api/core";
import type { BlockState, Position, ProjectResult, ProjectSummary, VoxelProposal } from "./types";

type Json = Record<string, unknown>;

function hasTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

const demo = (): VoxelProposal[] => {
  const voxels: VoxelProposal[] = [];
  const add = (position: Position, id: string, occupancy = 0.94, material = 0.86) => voxels.push({
    position, state: { id, properties: {} }, occupancyConfidence: occupancy, materialConfidence: material,
    alternatives: [], manual: false, evidence: [{ kind: "multi_view_surface", strength: occupancy }],
  });
  for (let x = -3; x <= 3; x++) for (let z = -3; z <= 3; z++) add([x, 0, z], "minecraft:oak_planks", 0.98, 0.92);
  for (let y = 1; y <= 3; y++) {
    for (let x = -3; x <= 3; x++) for (const z of [-3, 3]) add([x, y, z], "minecraft:stone_bricks");
    for (let z = -2; z <= 2; z++) for (const x of [-3, 3]) if (!(x === 3 && z === 0 && y < 3)) add([x, y, z], "minecraft:stone_bricks");
  }
  for (let x = -4; x <= 4; x++) for (let z = -4; z <= 4; z++) if (Math.abs(x) + Math.abs(z) <= 6) add([x, 4, z], "minecraft:dark_oak_planks", 0.89, 0.76);
  return voxels;
};

class BrowserDemo {
  voxels = demo();
  history: VoxelProposal[][] = [];
  future: VoxelProposal[][] = [];

  snapshot() { this.history.push(structuredClone(this.voxels)); this.future = []; }
  summary(): ProjectSummary { return { blockCount: this.voxels.length, lowConfidenceBlocks: this.voxels.filter((v) => Math.min(v.occupancyConfidence, v.materialConfidence) < 0.5).length, frameCount: 0, acceptedFrames: 0 }; }
  edit(position: Position, state: BlockState | null) {
    this.snapshot();
    this.voxels = this.voxels.filter((voxel) => voxel.position.some((value, index) => value !== position[index]));
    if (state?.id !== "minecraft:air") this.voxels.push({ position, state: state!, occupancyConfidence: 1, materialConfidence: 1, alternatives: [], manual: true });
  }
}

const browser = new BrowserDemo();

const browserVersions: Record<string, number> = {
  "1.20.4": 3700,
  "1.21.1": 3955,
  "1.21.4": 4189,
  "1.21.8": 4440,
  "1.21.9": 4554,
  "1.21.10": 4556,
  "1.21.11": 4671,
  "26.1": 4786,
  "26.1.1": 4788,
  "26.1.2": 4790,
  "26.2": 4903,
};

export async function rpc<T>(method: string, params: Json = {}): Promise<T> {
  if (hasTauri()) return invoke<T>("engine_request", { method, params });
  if (method === "engine.ping") return { ok: true, protocol: 1, demo: true } as T;
  if (method === "assets.list_supported") return { catalogSha256: "browser-demo", versions: Object.keys(browserVersions).map((id) => ({ id, installed: false })) } as T;
  if (method === "project.create" || method === "project.open") {
    const minecraftVersion = String(params.minecraftVersion ?? "26.2");
    return {
    path: String(params.path ?? params.project ?? "Browser demo"),
    config: { schemaVersion: 1, id: "browser-demo", name: String(params.name ?? "Courtyard Study"), createdAt: Date.now(), updatedAt: Date.now(), source: null, targetJavaVersion: minecraftVersion, minecraftDataVersion: browserVersions[minecraftVersion] ?? 4903, trims: null, masks: [], calibration: {}, pipelineHashes: {} },
    summary: browser.summary(),
    } as T;
  }
  if (method === "development.load_demo") return { blocks: browser.voxels.length, summary: browser.summary() } as T;
  if (method === "scene.voxels") return { voxels: browser.voxels, summary: browser.summary() } as T;
  const position = params.position as Position;
  if (method === "editing.paint") browser.edit(position, params.state as BlockState);
  else if (method === "editing.erase") browser.edit(position, null);
  else if (method === "editing.reset") browser.edit(position, null);
  else if (method === "editing.undo") { const value = browser.history.pop(); if (value) { browser.future.push(structuredClone(browser.voxels)); browser.voxels = value; } }
  else if (method === "editing.redo") { const value = browser.future.pop(); if (value) { browser.history.push(structuredClone(browser.voxels)); browser.voxels = value; } }
  else if (method === "export.write") throw new Error("Validated .litematic export is available in the Tauri desktop app or headless CLI.");
  return {} as T;
}

export async function projectCreate(path: string, name: string, minecraftVersion: string): Promise<ProjectResult> {
  return rpc("project.create", { path, name, minecraftVersion });
}
