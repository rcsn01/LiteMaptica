// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectResult } from "./types";

const mocks = vi.hoisted(() => ({
  chooseNewProjectPath: vi.fn(),
  chooseProjectDirectory: vi.fn(),
  chooseVideoFile: vi.fn(),
  chooseImageFolder: vi.fn(),
  rpc: vi.fn(),
}));

vi.mock("./dialogs", () => ({ ...mocks, isDesktopApp: () => true }));
vi.mock("./engine", () => ({ rpc: mocks.rpc }));
vi.mock("./VoxelViewer", () => ({ VoxelViewer: () => <div data-testid="viewer" /> }));

import App from "./App";

function project(name = "Test", source: Record<string, unknown> | null = null): ProjectResult {
  return {
    path: `/tmp/${name}.litemap`,
    config: {
      schemaVersion: 1, id: "id", name, createdAt: 1, updatedAt: 1, source,
      targetJavaVersion: "26.2", minecraftDataVersion: 4903, trims: null,
      masks: [], calibration: {}, pipelineHashes: {},
    },
    summary: { blockCount: 0, lowConfidenceBlocks: 0, frameCount: 0, acceptedFrames: 0 },
  };
}

describe("project and local source flows", () => {
  beforeEach(() => {
    mocks.chooseNewProjectPath.mockReset();
    mocks.chooseProjectDirectory.mockReset();
    mocks.chooseVideoFile.mockReset();
    mocks.chooseImageFolder.mockReset();
    mocks.rpc.mockReset();
    mocks.rpc.mockImplementation(async (method: string) => {
      if (method === "assets.list_supported") return { versions: [{ id: "26.2" }] };
      if (method === "scene.voxels") return { voxels: [], summary: project().summary };
      return { ok: true };
    });
  });

  afterEach(cleanup);

  it("creates a project after collecting its name and native save path", async () => {
    mocks.chooseNewProjectPath.mockResolvedValue("/tmp/My Project.litemap");
    mocks.rpc.mockImplementation(async (method: string, params: Record<string, unknown>) => {
      if (method === "assets.list_supported") return { versions: [{ id: "26.2" }] };
      if (method === "project.create") return project(String(params.name));
      if (method === "scene.voxels") return { voxels: [], summary: project().summary };
      return { ok: true };
    });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    fireEvent.change(screen.getByLabelText("PROJECT NAME"), { target: { value: "My Project" } });
    fireEvent.click(screen.getByRole("button", { name: "Choose location…" }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalledWith("project.create", expect.objectContaining({ name: "My Project", path: "/tmp/My Project.litemap" })));
    expect(await screen.findByRole("heading", { name: "My Project" })).toBeTruthy();
  });

  it("opens a project and imports a short local video", async () => {
    mocks.chooseProjectDirectory.mockResolvedValue("/tmp/Test.litemap");
    mocks.chooseVideoFile.mockResolvedValue("/tmp/walkthrough.mp4");
    mocks.rpc.mockImplementation(async (method: string) => {
      if (method === "assets.list_supported") return { versions: [{ id: "26.2" }] };
      if (method === "project.open") return project();
      if (method === "source.inspect") return { path: "/tmp/walkthrough.mp4", bytes: 10, duration: 75, width: 1920, height: 1080 };
      if (method === "source.import_local") return { path: "/tmp/walkthrough.mp4", bytes: 10, duration: 75, width: 1920, height: 1080, managedPath: "/tmp/Test.litemap/source/original.mp4" };
      if (method === "scene.voxels") return { voxels: [], summary: project().summary };
      return { ok: true };
    });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    await screen.findByRole("heading", { name: "Test" });
    fireEvent.click(screen.getByRole("button", { name: "Import video" }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalledWith("source.import_local", { project: "/tmp/Test.litemap", sourcePath: "/tmp/walkthrough.mp4" }));
    expect(await screen.findByText("walkthrough.mp4")).toBeTruthy();
    expect(screen.getByText("1:15")).toBeTruthy();
    expect(screen.getByText("1920 × 1080")).toBeTruthy();
  });

  it("imports a selected picture folder as reconstruction frames", async () => {
    mocks.chooseProjectDirectory.mockResolvedValue("/tmp/Test.litemap");
    mocks.chooseImageFolder.mockResolvedValue("/tmp/courtyard-views");
    mocks.rpc.mockImplementation(async (method: string) => {
      if (method === "assets.list_supported") return { versions: [{ id: "26.2" }] };
      if (method === "project.open") return project();
      if (method === "source.inspect_images") return { path: "/tmp/courtyard-views", folderName: "courtyard-views", count: 3, bytes: 30, width: 2048, height: 1152, mixedResolutions: false, order: "natural_filename" };
      if (method === "source.import_images") return { path: "/tmp/courtyard-views", folderName: "courtyard-views", count: 3, frameCount: 3, bytes: 30, width: 2048, height: 1152, mixedResolutions: false, order: "natural_filename", managedPath: "/tmp/Test.litemap/source/images" };
      if (method === "scene.voxels") return { voxels: [], summary: project().summary };
      return { ok: true };
    });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    await screen.findByRole("heading", { name: "Test" });
    fireEvent.click(screen.getByRole("button", { name: "Import pictures" }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalledWith("source.import_images", { project: "/tmp/Test.litemap", sourcePath: "/tmp/courtyard-views" }));
    expect(await screen.findByText("courtyard-views")).toBeTruthy();
    expect(screen.getByText("3 pictures · filename order")).toBeTruthy();
    expect(screen.getByText("2048 × 1152")).toBeTruthy();
  });
});
