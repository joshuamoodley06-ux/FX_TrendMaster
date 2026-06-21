import { describe, expect, it, vi } from 'vitest';
import { inspectorCommit, inspectorCommitOrThrow } from './inspectorCommit';

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

  it('routes structural range saves through the same hook', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, range_id: 42 }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const data = await inspectorCommitOrThrow({
      baseUrl: 'https://api.example.com/',
      kind: 'structural_range',
      source: 'structural_range_save',
      payload: { range_key: 'test_range' },
    });

    expect(data).toMatchObject({ range_id: 42 });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/v1/map/range',
      expect.objectContaining({ method: 'POST' }),
    );
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
