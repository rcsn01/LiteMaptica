export type Position = [number, number, number];

export interface BlockState {
  id: string;
  properties: Record<string, string>;
}

export interface Evidence {
  frameId?: number | null;
  kind: string;
  strength: number;
  details?: Record<string, unknown>;
}

export interface VoxelProposal {
  position: Position;
  state: BlockState;
  occupancyConfidence: number;
  materialConfidence: number;
  evidence?: Evidence[];
  alternatives: Array<{ state: BlockState; score: number }>;
  manual: boolean;
}

export interface ProjectConfig {
  schemaVersion: number;
  id: string;
  name: string;
  createdAt: number;
  updatedAt: number;
  source: null | Record<string, unknown>;
  targetJavaVersion: string;
  minecraftDataVersion: number;
  trims: null | { start: number; end: number };
  masks: unknown[];
  calibration: Record<string, unknown>;
  pipelineHashes: Record<string, string>;
}

export interface ProjectSummary {
  blockCount: number;
  lowConfidenceBlocks: number;
  frameCount: number;
  acceptedFrames: number;
}

export interface ProjectResult {
  path: string;
  config: ProjectConfig;
  summary: ProjectSummary;
}

export interface PipelineEvent {
  type: "progress" | "warning" | "recoverable_failure" | "needs_scale_anchors" | "needs_segment_alignment" | "completion" | "cancellation" | "fatal_failure";
  message?: string;
  stage?: string;
}

export interface PipelineJob {
  id: string;
  kind: string;
  status: "queued" | "running" | "paused" | "cancelled" | "completed" | "failed";
  stage: string;
  progress: number;
  report: { events: PipelineEvent[]; [key: string]: unknown };
}
