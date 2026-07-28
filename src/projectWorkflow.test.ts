import { describe, expect, it } from "vitest";
import {
  normalizeLitemapPath,
  sanitizeProjectName,
  validateTrim,
  videoDialogFilters,
} from "./projectWorkflow";

describe("project workflow validation", () => {
  it("normalizes a missing or mixed-case project suffix", () => {
    expect(normalizeLitemapPath("/tmp/My Build")).toBe("/tmp/My Build.litemap");
    expect(normalizeLitemapPath("/tmp/My Build.LITEMAP")).toBe("/tmp/My Build.litemap");
  });

  it("sanitizes project names for a suggested filename", () => {
    expect(sanitizeProjectName("  My / unsafe:* build. ")).toBe("My unsafe build");
    expect(sanitizeProjectName("... ")).toBe("Untitled Reconstruction");
  });

  it("validates trim bounds and the thirty-minute maximum", () => {
    expect(validateTrim({ start: 10, end: 20 }, 30)).toBeNull();
    expect(validateTrim({ start: -1, end: 20 }, 30)).toMatch(/Start/);
    expect(validateTrim({ start: 20, end: 20 }, 30)).toMatch(/Start/);
    expect(validateTrim({ start: 0, end: 31 }, 30)).toMatch(/duration/);
    expect(validateTrim({ start: 0, end: 1800.1 }, 2000)).toMatch(/30 minutes/);
  });

  it("constructs a single supported-video filter", () => {
    expect(videoDialogFilters()).toEqual([{ name: "Video", extensions: ["mp4", "mov", "webm"] }]);
  });
});
