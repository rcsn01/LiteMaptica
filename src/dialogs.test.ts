import { beforeEach, describe, expect, it, vi } from "vitest";

const dialog = vi.hoisted(() => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => dialog);

import { chooseImageFolder, chooseNewProjectPath, chooseProjectDirectory, chooseVideoFile } from "./dialogs";

describe("native dialog helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    dialog.open.mockReset();
    dialog.save.mockReset();
  });

  it("returns null when dialogs are cancelled", async () => {
    dialog.save.mockResolvedValue(null);
    dialog.open.mockResolvedValue(null);
    await expect(chooseNewProjectPath("Test")).resolves.toBeNull();
    await expect(chooseProjectDirectory()).resolves.toBeNull();
    await expect(chooseVideoFile()).resolves.toBeNull();
    await expect(chooseImageFolder()).resolves.toBeNull();
  });

  it("normalizes a save result and applies the video filter", async () => {
    dialog.save.mockResolvedValue("/tmp/Test");
    dialog.open.mockResolvedValue("/tmp/source.mp4");
    await expect(chooseNewProjectPath("Test")).resolves.toBe("/tmp/Test.litemap");
    await chooseVideoFile();
    expect(dialog.open).toHaveBeenCalledWith(expect.objectContaining({ filters: [{ name: "Video", extensions: ["mp4", "mov", "webm"] }] }));
  });

  it("opens picture sources as single folders", async () => {
    dialog.open.mockResolvedValue("/tmp/pictures");
    await expect(chooseImageFolder()).resolves.toBe("/tmp/pictures");
    expect(dialog.open).toHaveBeenCalledWith({ title: "Import picture folder", directory: true, multiple: false });
  });
});
