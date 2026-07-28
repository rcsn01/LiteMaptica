export const MAX_SOURCE_SECONDS = 30 * 60;
export const VIDEO_EXTENSIONS = ["mp4", "mov", "webm"] as const;

export interface VideoMetadata {
  path: string;
  bytes: number;
  duration: number | null;
  width?: number | null;
  height?: number | null;
  requiresTrim?: boolean;
  managedPath?: string;
}

export interface ImageFolderMetadata {
  path: string;
  folderName: string;
  count: number;
  bytes: number;
  width?: number | null;
  height?: number | null;
  mixedResolutions: boolean;
  resolutions?: Array<{ width: number; height: number }>;
  order: "natural_filename";
  managedPath?: string;
  frameCount?: number;
}

export interface TrimSelection {
  start: number;
  end: number;
}

export function sanitizeProjectName(value: string): string {
  const sanitized = value
    .trim()
    .replace(/[\u0000-\u001f\\/:*?"<>|]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[. ]+|[. ]+$/g, "")
    .slice(0, 80)
    .trim();
  return sanitized || "Untitled Reconstruction";
}

export function normalizeLitemapPath(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) throw new Error("Choose a location for the project.");
  if (/\.litemap$/i.test(trimmed)) return trimmed.replace(/\.litemap$/i, ".litemap");
  return `${trimmed}.litemap`;
}

export function isLitemapDirectory(path: string): boolean {
  return /\.litemap$/i.test(path.trim());
}

export function videoDialogFilters() {
  return [{ name: "Video", extensions: [...VIDEO_EXTENSIONS] }];
}

export function validateTrim(trim: TrimSelection, duration: number): string | null {
  if (![trim.start, trim.end, duration].every(Number.isFinite)) return "Enter valid start and end times.";
  if (trim.start < 0 || trim.start >= trim.end) return "Start must be at least 0 and before the end time.";
  if (trim.end > duration) return "End time cannot be later than the video duration.";
  if (trim.end - trim.start > MAX_SOURCE_SECONDS) return "The selected footage cannot exceed 30 minutes.";
  return null;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "Duration unavailable";
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remaining = rounded % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`
    : `${minutes}:${String(remaining).padStart(2, "0")}`;
}

export function fileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}
