import { afterEach, describe, expect, it, vi } from 'vitest';
import { inspectorCommit, inspectorCommitOrThrow } from './inspectorCommit';

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as typeof globalThis & { localMappingBridge?: unknown }).localMappingBridge;
});

describe('inspectorCommit', () => {
  it('posts raw mapping events through the single commit hook', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, event_id: 'evt-1' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit({
      baseUrl: 'https://api.example.com',
      kind: 'raw_mapping_event',
      source: 'manual_mark',
      payload: { event_id: 'evt-1', case_id: 'case-1' },
    });

    expect(result.ok).toBe(true);
    expect(result.kind).toBe('raw_mapping_event');
    expect(result.source).toBe('manual_mark');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/v1/raw-mapping/events',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('saves a structural edit locally before the backend write and returns processing state', async () => {
    const callOrder: string[] = [];
    const submit = vi.fn().mockImplementation(async () => {
      callOrder.push('local');
      return {
        ok: true,
        saved: true,
        state: 'SUCCESS',
        editId: 'fxedit-1',
        databasePath: 'C:/Users/Josh/Documents/FXTM_Research/range_library_memory.sqlite3',
        electronDatabasePath: 'C:/Users/Josh/Documents/FXTM_Research/range_library_memory.sqlite3',
        pythonDatabasePath: 'C:/Users/Josh/Documents/FXTM_Research/range_library_memory.sqlite3',
        sameDatabasePath: true,
      };
    });
    (globalThis as typeof globalThis & { localMappingBridge?: unknown }).localMappingBridge = { submit };
    const fetchMock = vi.fn().mockImplementation(async () => {
      callOrder.push('backend');
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, range_id: 42 }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit<{ ok: boolean; range_id: number; local_processing?: unknown }>({
      baseUrl: 'https://api.example.com/',
      kind: 'structural_range',
      source: 'structural_range_save',
      payload: { range_key: 'test_range' },
    });

    expect(callOrder).toEqual(['local', 'backend']);
    expect(result.ok).toBe(true);
    expect(result.localProcessing).toMatchObject({ state: 'SUCCESS', sameDatabasePath: true });
    expect(result.data?.local_processing).toMatchObject({ editId: 'fxedit-1' });
  });

  it('blocks the backend write when local durability fails', async () => {
    (globalThis as typeof globalThis & { localMappingBridge?: unknown }).localMappingBridge = {
      submit: vi.fn().mockResolvedValue({
        ok: false,
        saved: false,
        state: 'FAILED',
        error: 'disk full',
      }),
    };
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit({
      baseUrl: 'https://api.example.com',
      kind: 'structural_event',
      source: 'structural_bos',
      payload: { event_id: 'evt-2' },
    });

    expect(result.ok).toBe(false);
    expect(result.error).toBe('disk full');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps backend save available when Python processing fails after the edit was saved', async () => {
    (globalThis as typeof globalThis & { localMappingBridge?: unknown }).localMappingBridge = {
      submit: vi.fn().mockResolvedValue({
        ok: false,
        saved: true,
        state: 'FAILED',
        editId: 'fxedit-2',
        error: 'processor crashed',
      }),
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, event_id: 'evt-2' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit({
      baseUrl: 'https://api.example.com',
      kind: 'structural_event',
      source: 'structural_bos',
      payload: { event_id: 'evt-2' },
    });

    expect(result.ok).toBe(true);
    expect(result.localProcessing).toMatchObject({ saved: true, state: 'FAILED' });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('throws on backend failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ ok: false, error: 'server meltdown' }),
      }),
    );

    await expect(
      inspectorCommitOrThrow({
        baseUrl: 'https://api.example.com',
        kind: 'structural_event',
        source: 'structural_quick_button',
        payload: {},
      }),
    ).rejects.toThrow('server meltdown');
  });

  it('patches structural events by event id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await inspectorCommitOrThrow({
      baseUrl: 'https://api.example.com',
      kind: 'structural_event_patch',
      source: 'structural_undo',
      pathParams: { eventId: 'abc-123' },
      payload: { meta_json: { undone: true } },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/v1/map/structural-event/abc-123',
      expect.objectContaining({ method: 'PATCH' }),
    );
  });
});
