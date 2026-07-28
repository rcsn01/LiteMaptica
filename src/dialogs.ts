import { open, save } from "@tauri-apps/plugin-dialog";
import { normalizeLitemapPath, sanitizeProjectName, videoDialogFilters } from "./projectWorkflow";

export function isDesktopApp(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function chooseNewProjectPath(suggestedName: string): Promise<string | null> {
  if (!isDesktopApp()) return null;
  const selected = await save({
    title: "Create LiteMaptica project",
    defaultPath: `${sanitizeProjectName(suggestedName)}.litemap`,
    filters: [{ name: "LiteMaptica Project", extensions: ["litemap"] }],
  });
  return selected ? normalizeLitemapPath(selected) : null;
}

export async function chooseProjectDirectory(): Promise<string | null> {
  if (!isDesktopApp()) return null;
  const selected = await open({ title: "Open LiteMaptica project", directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}

export async function chooseVideoFile(): Promise<string | null> {
  if (!isDesktopApp()) return null;
  const selected = await open({ title: "Import source video", directory: false, multiple: false, filters: videoDialogFilters() });
  return typeof selected === "string" ? selected : null;
}

export async function chooseImageFolder(): Promise<string | null> {
  if (!isDesktopApp()) return null;
  const selected = await open({ title: "Import picture folder", directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}
