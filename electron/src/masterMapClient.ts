import {
  adaptMasterMapOutput,
  type MasterMapDocument,
} from './masterMapAdapter';

export type PersistedMasterMapResponse = {
  ok: boolean;
  symbol?: string;
  databasePath?: string;
  masterMap?: unknown;
  error?: string;
};

export type MasterMapBridge = {
  getMasterMap: (symbol?: string) => Promise<PersistedMasterMapResponse>;
};

export type PersistedMasterMapLoadResult =
  | {
      ok: true;
      document: MasterMapDocument;
      databasePath: string;
    }
  | {
      ok: false;
      document: null;
      databasePath: string;
      error: string;
    };

export function getMasterMapBridge(): MasterMapBridge | null {
  const bridge = (globalThis as typeof globalThis & {
    localMappingBridge?: Partial<MasterMapBridge>;
  }).localMappingBridge;
  return bridge?.getMasterMap ? bridge as MasterMapBridge : null;
}

export async function loadPersistedMasterMap(
  symbol = 'XAUUSD',
  bridge: MasterMapBridge | null = getMasterMapBridge(),
): Promise<PersistedMasterMapLoadResult> {
  if (!bridge) {
    return {
      ok: false,
      document: null,
      databasePath: '',
      error: 'Master Map bridge unavailable. Open the hierarchy in Electron.',
    };
  }
  try {
    const response = await bridge.getMasterMap(symbol);
    const databasePath = String(response.databasePath || '');
    if (!response.ok || !response.masterMap) {
      return {
        ok: false,
        document: null,
        databasePath,
        error: response.error || `No persisted ${symbol.toUpperCase()} Master Map is available.`,
      };
    }
    return {
      ok: true,
      document: adaptMasterMapOutput(response.masterMap),
      databasePath,
    };
  } catch (error) {
    return {
      ok: false,
      document: null,
      databasePath: '',
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
