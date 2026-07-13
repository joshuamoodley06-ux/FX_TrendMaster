import { afterEach, describe, expect, it, vi } from 'vitest';
import { inspectorCommit, inspectorCommitOrThrow } from './inspectorCommit';

type Bridge = {
  submit: ReturnType<typeof vi.fn>;
  backendSucceeded: ReturnType<typeof vi.fn>;
  backendFailed: ReturnType<typeof vi.fn>;
  retry: ReturnType<typeof vi.fn>;
};

function installBridge(overrides: Partial<Bridge> = {}): Bridge {
  const bridge: Bridge = {
    submit: vi.fn().mockResolvedValue({ ok: true, saved: true, state: 'PENDING', status: 'AWAITING_BACKEND', editId: 'edit-1', backendStatus: 'UNCONFIRMED' }),
    backendSucceeded: vi.fn().mockResolvedValue({ ok: true, saved: true, state: 'SUCCESS', status: 'PROCESSED', editId: 'edit-1', backendStatus: 'CONFIRMED', backendRangeId: '42' }),
    backendFailed: vi.fn().mockResolvedValue({ ok: false, saved: true, state: 'FAILED', status: 'BACKEND_REJECTED', editId: 'edit-1', backendStatus: 'REJECTED' }),
    retry: vi.fn().mockResolvedValue({ ok: true, saved: true, state: 'SUCCESS', status: 'PROCESSED', editId: 'edit-1', backendStatus: 'CONFIRMED', backendResponse: { ok: true, range_id: 42 } }),
    ...overrides,
  };
  (globalThis as typeof globalThis & { localMappingBridge?: Bridge }).localMappingBridge = bridge;
  return bridge;
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as typeof globalThis & { localMappingBridge?: Bridge }).localMappingBridge;
});

describe('inspectorCommit', () => {
  it('posts non-structural raw mapping events without using the local structural bridge', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true, event_id: 'evt-1' }) });
    vi.stubGlobal('fetch', fetchMock);
    const result = await inspectorCommit({ baseUrl: 'https://api.example.com', kind: 'raw_mapping_event', source: 'manual_mark', payload: { event_id: 'evt-1' } });
    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('durably stores the instruction, waits for backend success, then confirms and processes it', async () => {
    const order: string[] = [];
    const bridge = installBridge({
      submit: vi.fn().mockImplementation(async () => {
        order.push('local-instruction');
        return { ok: true, saved: true, state: 'PENDING', status: 'AWAITING_BACKEND', editId: 'edit-1', backendStatus: 'UNCONFIRMED' };
      }),
      backendSucceeded: vi.fn().mockImplementation(async () => {
        order.push('python-after-backend');
        return { ok: true, saved: true, state: 'SUCCESS', status: 'PROCESSED', editId: 'edit-1', backendStatus: 'CONFIRMED', backendRangeId: '42' };
      }),
    });
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      order.push('backend');
      return { ok: true, status: 200, json: async () => ({ ok: true, range_id: 42 }) };
    }));

    const result = await inspectorCommit({ baseUrl: 'https://api.example.com', kind: 'structural_range', source: 'structural_range_save', payload: { symbol: 'XAUUSD' } });

    expect(order).toEqual(['local-instruction', 'backend', 'python-after-backend']);
    expect(bridge.backendSucceeded).toHaveBeenCalledWith('edit-1', { ok: true, range_id: 42 }, 200);
    expect(result.localProcessing).toMatchObject({ state: 'SUCCESS', backendRangeId: '42' });
  });

  it('preserves a backend rejection and never asks Python to process it', async () => {
    const bridge = installBridge();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ ok: false, error: 'parent mismatch' }) }));

    const result = await inspectorCommit({ baseUrl: 'https://api.example.com', kind: 'structural_event', source: 'structural_bos', payload: { event_type: 'BOS_UP' } });

    expect(result.ok).toBe(false);
    expect(bridge.backendFailed).toHaveBeenCalledWith('edit-1', {
      error: 'parent mismatch', response: { ok: false, error: 'parent mismatch' }, httpStatus: 409,
    });
    expect(bridge.backendSucceeded).not.toHaveBeenCalled();
    expect(bridge.retry).not.toHaveBeenCalled();
  });

  it('does not repeat the backend save when the same durable edit is already confirmed', async () => {
    const bridge = installBridge({
      submit: vi.fn().mockResolvedValue({ ok: true, saved: true, state: 'FAILED', status: 'PYTHON_FAILED', editId: 'edit-1', backendStatus: 'CONFIRMED', backendResponse: { ok: true, range_id: 42 } }),
    });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit<{ ok: boolean; range_id: number }>({ baseUrl: 'https://api.example.com', kind: 'structural_range', source: 'structural_range_save', payload: { symbol: 'XAUUSD' } });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(bridge.retry).toHaveBeenCalledWith('edit-1');
    expect(result.ok).toBe(true);
    expect(result.data).toMatchObject({ range_id: 42 });
  });

  it('blocks backend work only when the original instruction cannot be saved locally', async () => {
    installBridge({ submit: vi.fn().mockResolvedValue({ ok: false, saved: false, state: 'FAILED', error: 'disk full' }) });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const result = await inspectorCommit({ baseUrl: 'https://api.example.com', kind: 'structural_range', source: 'structural_range_save', payload: {} });
    expect(result.error).toBe('disk full');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('throws on backend failure through inspectorCommitOrThrow', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({ ok: false, error: 'server meltdown' }) }));
    await expect(inspectorCommitOrThrow({ baseUrl: 'https://api.example.com', kind: 'structural_event', source: 'structural_quick_button', payload: {} })).rejects.toThrow('server meltdown');
  });
});
