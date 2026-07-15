import {
  adaptMappingAssistantSnapshot,
  type MappingAssistantSnapshot,
} from './mappingAssistantModel';

export type MappingAssistantRunnerResult = {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  error?: string;
  parsed?: unknown;
};

export type MappingAssistantBridge = {
  getPaths: () => Promise<{ ok: boolean; databasePath?: string; error?: string }>;
  runMappingAssistant: (args: {
    databasePath: string;
    symbol?: 'XAUUSD';
    pythonPath?: string;
  }) => Promise<MappingAssistantRunnerResult>;
};

export type MappingAssistantPathBridge = {
  getPaths: () => Promise<{ ok: boolean; databasePath?: string; error?: string }>;
};

export type MappingAssistantLoadResult =
  | { ok: true; snapshot: MappingAssistantSnapshot; databasePath: string }
  | { ok: false; snapshot: null; databasePath: string; error: string };

declare global {
  interface Window {
    localResearch?: Partial<MappingAssistantBridge>;
    localMappingBridge?: Partial<MappingAssistantPathBridge>;
  }
}

export function getMappingAssistantBridge(): MappingAssistantBridge | null {
  const bridge = globalThis.localResearch;
  return bridge?.runMappingAssistant && bridge?.getPaths
    ? bridge as MappingAssistantBridge
    : null;
}

export function getMappingAssistantPathBridge(): MappingAssistantPathBridge | null {
  const bridge = globalThis.localMappingBridge;
  return bridge?.getPaths ? bridge as MappingAssistantPathBridge : null;
}

function parseRunnerPayload(result: MappingAssistantRunnerResult): unknown {
  if (result.parsed !== undefined && result.parsed !== null) return result.parsed;
  const raw = String(result.stdout || '').trim();
  if (!raw) throw new Error('Mapping Assistant returned no JSON payload.');
  return JSON.parse(raw);
}

export async function loadMappingAssistant(
  bridge: MappingAssistantBridge | null = getMappingAssistantBridge(),
  pathBridge: MappingAssistantPathBridge | null = getMappingAssistantPathBridge(),
): Promise<MappingAssistantLoadResult> {
  if (!bridge) {
    return {
      ok: false,
      snapshot: null,
      databasePath: '',
      error: 'Mapping Assistant bridge unavailable. Start the Electron desktop app.',
    };
  }
  try {
    const pathResult = pathBridge
      ? await pathBridge.getPaths()
      : await bridge.getPaths();
    const databasePath = String(pathResult.databasePath || '').trim();
    if (!pathResult.ok || !databasePath) {
      return {
        ok: false,
        snapshot: null,
        databasePath,
        error: pathResult.error || 'Range Library database path is unavailable.',
      };
    }
    const result = await bridge.runMappingAssistant({
      databasePath,
      symbol: 'XAUUSD',
    });
    if (!result.ok) {
      return {
        ok: false,
        snapshot: null,
        databasePath,
        error: result.error || result.stderr || 'Mapping Assistant Python run failed.',
      };
    }
    const snapshot = adaptMappingAssistantSnapshot(parseRunnerPayload(result));
    return { ok: true, snapshot, databasePath };
  } catch (error) {
    return {
      ok: false,
      snapshot: null,
      databasePath: '',
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
