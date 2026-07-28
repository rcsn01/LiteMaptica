import { useCallback, useEffect, useMemo, useState } from "react";
import { chooseImageFolder, chooseNewProjectPath, chooseProjectDirectory, chooseVideoFile, isDesktopApp } from "./dialogs";
import { rpc } from "./engine";
import { displayName } from "./palette";
import {
  MAX_SOURCE_SECONDS,
  fileName,
  formatDuration,
  isLitemapDirectory,
  sanitizeProjectName,
  validateTrim,
  type ImageFolderMetadata,
  type TrimSelection,
  type VideoMetadata,
} from "./projectWorkflow";
import type { BlockState, ProjectResult, ProjectSummary, VoxelProposal } from "./types";
import { VoxelViewer } from "./VoxelViewer";
import "@moirasia/ui-css/litemaptica.css";
import "./styles.css";

const blocks = ["minecraft:stone_bricks", "minecraft:oak_planks", "minecraft:dark_oak_planks", "minecraft:bricks", "minecraft:glass", "minecraft:mossy_stone_bricks"];
const fallbackVersions = ["1.20.4", "1.21.1", "1.21.4", "1.21.8", "1.21.9", "1.21.10", "1.21.11", "26.1", "26.1.1", "26.1.2", "26.2"];

interface PendingVideo {
  path: string;
  metadata: VideoMetadata;
  trim: TrimSelection;
}

type SourceDisplay =
  | { kind: "video"; name: string; metadata: VideoMetadata }
  | { kind: "pictures"; name: string; metadata: ImageFolderMetadata };

function configSource(project: ProjectResult | null): SourceDisplay | null {
  const source = project?.config.source;
  if (!source || typeof source.metadata !== "object" || !source.metadata) return null;
  if (source.kind === "local") return {
    kind: "video",
    name: typeof source.originalName === "string" ? source.originalName : "Imported video",
    metadata: source.metadata as unknown as VideoMetadata,
  };
  if (source.kind === "image_folder") return {
    kind: "pictures",
    name: typeof source.originalName === "string" ? source.originalName : "Imported pictures",
    metadata: source.metadata as unknown as ImageFolderMetadata,
  };
  return null;
}

export default function App() {
  const desktop = isDesktopApp();
  const [project, setProject] = useState<ProjectResult | null>(null);
  const [voxels, setVoxels] = useState<VoxelProposal[]>([]);
  const [summary, setSummary] = useState<ProjectSummary>({ blockCount: 0, lowConfidenceBlocks: 0, frameCount: 0, acceptedFrames: 0 });
  const [selected, setSelected] = useState<VoxelProposal | null>(null);
  const [blockId, setBlockId] = useState(blocks[0]);
  const [confidenceMode, setConfidenceMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(desktop ? "Ready for a new reconstruction" : "Desktop app required for project and source chooser actions.");
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("Untitled Reconstruction");
  const [minecraftVersion, setMinecraftVersion] = useState("26.2");
  const [versions, setVersions] = useState(fallbackVersions);
  const [projectError, setProjectError] = useState("");
  const [pendingVideo, setPendingVideo] = useState<PendingVideo | null>(null);
  const [trimError, setTrimError] = useState("");
  const [source, setSource] = useState<SourceDisplay | null>(null);
  const [importProgress, setImportProgress] = useState<number | null>(null);

  const call = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async (path?: string) => {
    const projectPath = path ?? project?.path;
    if (!projectPath) return;
    const result = await rpc<{ voxels: VoxelProposal[]; summary: ProjectSummary }>("scene.voxels", { project: projectPath, includeEvidence: true });
    setVoxels(result.voxels);
    setSummary(result.summary);
    setSelected((current) => current ? result.voxels.find((item) => item.position.every((value, index) => value === current.position[index])) ?? null : null);
  }, [project?.path]);

  const acceptProject = useCallback(async (result: ProjectResult) => {
    setProject(result);
    setSource(configSource(result));
    setSelected(null);
    await refresh(result.path);
  }, [refresh]);

  const openProject = () => call(async () => {
    if (!desktop) throw new Error("Desktop app required to choose a project directory.");
    const path = await chooseProjectDirectory();
    if (!path) return;
    if (!isLitemapDirectory(path)) throw new Error("Choose a directory ending in .litemap.");
    const result = await rpc<ProjectResult>("project.open", { project: path });
    await acceptProject(result);
    setNotice("Project opened and validated.");
  });

  const createProject = async () => {
    setProjectError("");
    const name = sanitizeProjectName(newProjectName);
    setBusy(true);
    try {
      const path = await chooseNewProjectPath(name);
      if (!path) return;
      const result = await rpc<ProjectResult>("project.create", { path, name, minecraftVersion });
      await acceptProject(result);
      setNewProjectOpen(false);
      setNotice("Project created. Import source footage when ready.");
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const finishImport = async (path: string, metadata: VideoMetadata, trim?: TrimSelection) => {
    if (!project) return;
    setBusy(true);
    setImportProgress(55);
    setNotice("Copying video into the project…");
    try {
      const imported = await rpc<VideoMetadata>("source.import_local", { project: project.path, sourcePath: path, ...(trim ? { trim } : {}) });
      setImportProgress(90);
      const reopened = await rpc<ProjectResult>("project.open", { project: project.path });
      await acceptProject(reopened);
      setSource({ kind: "video", name: fileName(path), metadata: { ...metadata, ...imported } });
      setPendingVideo(null);
      setTrimError("");
      setImportProgress(100);
      setNotice("Source ready.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setImportProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const importVideo = async () => {
    if (!desktop || !project) return;
    setBusy(true);
    try {
      const path = await chooseVideoFile();
      if (!path) return;
      setImportProgress(15);
      setNotice("Inspecting source video…");
      const metadata = await rpc<VideoMetadata>("source.inspect", { path });
      setImportProgress(35);
      if (metadata.duration != null && (metadata.requiresTrim || metadata.duration > MAX_SOURCE_SECONDS)) {
        setPendingVideo({ path, metadata, trim: { start: 0, end: Math.min(metadata.duration, MAX_SOURCE_SECONDS) } });
        setTrimError("");
        setImportProgress(null);
        setNotice("Choose up to 30 minutes of source footage.");
        return;
      }
      await finishImport(path, metadata);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setImportProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const importPictures = async () => {
    if (!desktop || !project) return;
    setBusy(true);
    try {
      const path = await chooseImageFolder();
      if (!path) return;
      setImportProgress(15);
      setNotice("Inspecting picture folder…");
      const metadata = await rpc<ImageFolderMetadata>("source.inspect_images", { path });
      setImportProgress(40);
      setNotice(`Copying ${metadata.count.toLocaleString()} pictures into the project…`);
      const imported = await rpc<ImageFolderMetadata>("source.import_images", { project: project.path, sourcePath: path });
      setImportProgress(90);
      const reopened = await rpc<ProjectResult>("project.open", { project: project.path });
      await acceptProject(reopened);
      setSource({ kind: "pictures", name: metadata.folderName || fileName(path), metadata: { ...metadata, ...imported } });
      setImportProgress(100);
      setNotice(`${imported.frameCount ?? imported.count} pictures ready as reconstruction frames.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setImportProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const confirmTrim = async () => {
    if (!pendingVideo?.metadata.duration) return;
    const error = validateTrim(pendingVideo.trim, pendingVideo.metadata.duration);
    if (error) {
      setTrimError(error);
      return;
    }
    await finishImport(pendingVideo.path, pendingVideo.metadata, pendingVideo.trim);
  };

  const loadDemo = () => project && call(async () => {
    await rpc("development.load_demo", { project: project.path });
    await refresh(project.path);
    setNotice("Evidence-backed fixture loaded.");
  });

  const edit = (method: "paint" | "erase" | "reset") => {
    if (!project || !selected) return;
    call(async () => {
      const params: Record<string, unknown> = { project: project.path, position: selected.position };
      if (method === "paint") params.state = { id: blockId, properties: {} } satisfies BlockState;
      await rpc(`editing.${method}`, params);
      await refresh();
      setNotice(`${method[0].toUpperCase() + method.slice(1)} saved transactionally.`);
    });
  };

  const history = (method: "undo" | "redo") => project && call(async () => {
    await rpc(`editing.${method}`, { project: project.path });
    await refresh();
    setNotice(`${method === "undo" ? "Undid" : "Redid"} the last edit.`);
  });

  const exportFile = () => project && call(async () => {
    const destination = `${project.path}/exports/${project.config.name}.litematic`;
    const result = await rpc<{ blocks: number; path: string }>("export.write", { project: project.path, destination });
    setNotice(`Validated ${result.blocks.toLocaleString()} blocks → ${result.path}`);
  });

  useEffect(() => {
    rpc<{ versions: Array<{ id: string }> }>("assets.list_supported")
      .then((result) => setVersions(result.versions.map(({ id }) => id)))
      .catch(() => undefined);
    rpc("engine.ping").catch(() => setNotice("Engine is unavailable."));
  }, []);

  const confidence = selected ? Math.min(selected.occupancyConfidence, selected.materialConfidence) : 0;
  const coverage = useMemo(() => summary.blockCount ? Math.round((summary.blockCount - summary.lowConfidenceBlocks) / summary.blockCount * 100) : 0, [summary]);
  const sourceState = source ? (source.kind === "pictures" ? `${source.metadata.count} pictures ready` : "Source ready") : "Awaiting footage";
  const desktopTitle = desktop ? undefined : "Desktop app required";

  return <main className="app-shell">
    <header className="topbar" data-tauri-drag-region>
      <div className="brand" data-tauri-drag-region><span className="brand-mark" data-tauri-drag-region>L</span><div data-tauri-drag-region><strong data-tauri-drag-region>LiteMaptica</strong><small data-tauri-drag-region>EVIDENCE → BLOCKS</small></div></div>
      <div className="project-controls" data-tauri-drag-region>
        <button onClick={openProject} disabled={busy || !desktop} title={desktopTitle}>Open project</button>
        <button className="primary" onClick={() => { setProjectError(""); setNewProjectOpen(true); }} disabled={busy || !desktop} title={desktopTitle}>New project</button>
      </div>
      <div className={`engine-status ${busy ? "busy" : ""}`} data-tauri-drag-region><i data-tauri-drag-region />{busy ? "Working" : "Engine ready"}</div>
    </header>
    <section className="workspace">
      <aside className="rail">
        <div className="rail-section"><label>PROJECT</label><h1>{project?.config.name ?? "No project open"}</h1><p>{project?.config.targetJavaVersion ? `Java ${project.config.targetJavaVersion} · DataVersion ${project.config.minecraftDataVersion}` : "Create or open a .litemap directory"}</p></div>
        <div className="stage-list">
          {[["01", "Source", sourceState], ["02", "Geometry", "Not run"], ["03", "Block solve", "Not run"], ["04", "Review", voxels.length ? "Active" : "Awaiting result"]].map(([number, name, state]) => <div className={`stage ${(name === "Source" && source) || (name === "Review" && voxels.length) ? "active" : ""}`} key={name}><span>{number}</span><div><b>{name}</b><small>{state}</small></div></div>)}
        </div>
        {source && <div className="source-card"><label>SOURCE READY</label><strong>{source.name}</strong><span>{source.kind === "pictures" ? `${source.metadata.count.toLocaleString()} pictures · filename order` : formatDuration(source.metadata.duration)}</span><span>{source.metadata.width && source.metadata.height ? `${source.metadata.width} × ${source.metadata.height}` : source.kind === "pictures" && source.metadata.mixedResolutions ? "Mixed resolutions" : "Resolution unavailable"}</span></div>}
        <div className="source-actions"><button className="import" disabled={!project || busy || !desktop} onClick={importVideo} title={!desktop ? desktopTitle : !project ? "Open a project first" : undefined}>Import video</button><button className="import pictures" disabled={!project || busy || !desktop} onClick={importPictures} title={!desktop ? desktopTitle : !project ? "Open a project first" : undefined}>Import pictures</button></div>
        {importProgress != null && <div className="import-progress" aria-label="Import progress"><i style={{ width: `${importProgress}%` }} /></div>}
        <button className="fixture" disabled={!project || busy} onClick={loadDemo}>Load evidence fixture</button>
        <div className="rail-note">{desktop ? "Import replaces the current source. Pictures are ordered naturally by filename and stored as reconstruction frames." : "Desktop app required for native project and source choosers."}</div>
      </aside>
      <section className="canvas-panel">
        <div className="canvas-toolbar">
          <div><button className={!confidenceMode ? "selected" : ""} onClick={() => setConfidenceMode(false)}>Block material</button><button className={confidenceMode ? "selected" : ""} onClick={() => setConfidenceMode(true)}>Confidence</button></div>
          <div className="legend"><span className="high" />High <span className="low" />Low</div>
        </div>
        <VoxelViewer voxels={voxels} confidenceMode={confidenceMode} selected={selected} onSelect={setSelected} />
        <div className="notice">{notice}</div>
      </section>
      <aside className="inspector">
        <label>INSPECTOR</label>
        {selected ? <>
          <div className="block-title"><span style={{ background: `#${(confidenceMode ? 74 << 16 | 205 << 8 | 118 : 0x8b8b86).toString(16).padStart(6, "0")}` }} /><div><h2>{displayName(selected.state.id)}</h2><code>{selected.position.join(", ")}</code></div></div>
          <div className="meter-label"><span>Occupancy</span><b>{Math.round(selected.occupancyConfidence * 100)}%</b></div><div className="meter"><i style={{ width: `${selected.occupancyConfidence * 100}%` }} /></div>
          <div className="meter-label"><span>Material</span><b>{Math.round(selected.materialConfidence * 100)}%</b></div><div className="meter amber"><i style={{ width: `${selected.materialConfidence * 100}%` }} /></div>
          <div className="confidence-badge">{confidence >= .9 ? "High" : confidence >= .6 ? "Medium" : "Low"} confidence · {selected.manual ? "Manual edit" : `${selected.evidence?.length ?? 0} evidence item(s)`}</div>
          <hr /><label>EDIT BLOCK</label><select value={blockId} onChange={(e) => setBlockId(e.target.value)}>{blocks.map((id) => <option key={id} value={id}>{displayName(id)}</option>)}</select>
          <div className="button-grid"><button onClick={() => edit("paint")}>Paint</button><button onClick={() => edit("erase")}>Erase</button><button onClick={() => edit("reset")}>Reset auto</button></div>
        </> : <div className="empty-inspector"><div className="cube-icon">◇</div><p>Select a block to inspect its state, confidence, evidence, and alternatives.</p></div>}
        <div className="inspector-bottom"><div className="button-grid two"><button onClick={() => history("undo")}>↶ Undo</button><button onClick={() => history("redo")}>↷ Redo</button></div><button className="export" disabled={!voxels.length || busy} onClick={exportFile}>Export validated .litematic</button></div>
      </aside>
    </section>
    <footer><span><b>{summary.blockCount.toLocaleString()}</b> evidenced blocks</span><span><b>{coverage}%</b> above review threshold</span><span><b>{summary.lowConfidenceBlocks}</b> low confidence</span><span className="local">● Local processing · telemetry off</span></footer>

    {newProjectOpen && <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-project-title">
        <label>NEW PROJECT</label><h2 id="new-project-title">Create reconstruction</h2>
        <label htmlFor="project-name">PROJECT NAME</label><input id="project-name" autoFocus value={newProjectName} onChange={(event) => setNewProjectName(event.target.value)} />
        <label htmlFor="minecraft-version">TESTED MINECRAFT VERSION</label><select id="minecraft-version" value={minecraftVersion} onChange={(event) => setMinecraftVersion(event.target.value)}>{versions.map((version) => <option key={version}>{version}</option>)}</select>
        {projectError && <p className="inline-error" role="alert">{projectError}</p>}
        <div className="modal-actions"><button onClick={() => setNewProjectOpen(false)} disabled={busy}>Cancel</button><button className="primary" onClick={createProject} disabled={busy}>Choose location…</button></div>
      </section>
    </div>}

    {pendingVideo && <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="trim-title">
        <label>TRIM SOURCE</label><h2 id="trim-title">Select up to 30 minutes</h2><p className="modal-copy">{fileName(pendingVideo.path)} · {formatDuration(pendingVideo.metadata.duration)}</p>
        <div className="trim-grid"><div><label htmlFor="trim-start">START (SECONDS)</label><input id="trim-start" type="number" min="0" step="0.1" value={pendingVideo.trim.start} onChange={(event) => setPendingVideo({ ...pendingVideo, trim: { ...pendingVideo.trim, start: Number(event.target.value) } })} /></div><div><label htmlFor="trim-end">END (SECONDS)</label><input id="trim-end" type="number" min="0" max={pendingVideo.metadata.duration ?? undefined} step="0.1" value={pendingVideo.trim.end} onChange={(event) => setPendingVideo({ ...pendingVideo, trim: { ...pendingVideo.trim, end: Number(event.target.value) } })} /></div></div>
        {trimError && <p className="inline-error" role="alert">{trimError}</p>}
        <div className="modal-actions"><button onClick={() => { setPendingVideo(null); setTrimError(""); }} disabled={busy}>Cancel</button><button className="primary" onClick={confirmTrim} disabled={busy}>Import selection</button></div>
      </section>
    </div>}
  </main>;
}
