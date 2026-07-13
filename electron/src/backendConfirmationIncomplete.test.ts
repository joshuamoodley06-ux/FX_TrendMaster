import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { inspectorCommit } from './inspectorCommit';

const require = createRequire(import.meta.url);
const { DatabaseSync } = require('node:sqlite');
const { createLocalMappingBridgeService } = require('../electron/localMappingBridge.cjs') as {
  createLocalMappingBridgeService: (options: Record<string, unknown>) => any;
};

const roots: string[] = [];
function tempDb(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-confirmation-incomplete-'));
  roots.push(root);
  return path.join(root, 'range_library_memory.sqlite3');
}
afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as typeof globalThis & { localMappingBridge?: unknown }).localMappingBridge;
  for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe('backend confirmation incomplete', () => {
  it('keeps HTTP success without final range_id unresolved across restart and never runs Python', async () => {
    const databasePath = tempDb();
    const calls = { value: 0 };
    const processor = async () => { calls.value += 1; return { ok: true }; };
    let service = createLocalMappingBridgeService({ databasePath, processor });
    const request = {
      kind: 'structural_range',
      source: 'structural_range_save',
      payload: { case_ref: 'case-A', symbol: 'XAUUSD', provisional_id: 'draft-1' },
    };
    const saved = await service.prepare(request);
    const backendResponse = { ok: true, message: 'saved', range: { status: 'ACTIVE' } };
    const unresolved = await service.backendSucceeded(saved.editId, backendResponse, 200);

    expect(unresolved).toMatchObject({
      state: 'FAILED',
      status: 'BACKEND_CONFIRMATION_INCOMPLETE',
      backendStatus: 'RESPONSE_INVALID',
      backendHttpStatus: 200,
      backendResponse,
      backendRangeId: null,
      backendEventId: null,
      attemptCount: 0,
    });
    expect(calls.value).toBe(0);
    expect((await service.resumePending()).resumed).toBe(0);

    const db = new DatabaseSync(databasePath);
    db.exec('CREATE TABLE IF NOT EXISTS raw_ranges(id INTEGER PRIMARY KEY); CREATE TABLE IF NOT EXISTS raw_events(id INTEGER PRIMARY KEY);');
    expect(db.prepare('SELECT COUNT(*) AS n FROM raw_ranges').get().n).toBe(0);
    expect(db.prepare('SELECT COUNT(*) AS n FROM raw_events').get().n).toBe(0);
    const persisted = db.prepare(`SELECT payload_json, backend_response_json, backend_status, status,
      backend_confirmed_payload_json, backend_range_id, backend_event_id
      FROM local_mapping_edits WHERE edit_id=?`).get(saved.editId);
    expect(JSON.parse(String(persisted.payload_json)).payload).toMatchObject(request.payload);
    expect(JSON.parse(String(persisted.backend_response_json))).toEqual(backendResponse);
    expect(persisted).toMatchObject({
      backend_status: 'RESPONSE_INVALID',
      status: 'BACKEND_CONFIRMATION_INCOMPLETE',
      backend_confirmed_payload_json: null,
      backend_range_id: null,
      backend_event_id: null,
    });
    db.close();
    service.close();

    service = createLocalMappingBridgeService({ databasePath, processor });
    expect(service.getStatus(saved.editId)).toMatchObject({
      state: 'FAILED',
      status: 'BACKEND_CONFIRMATION_INCOMPLETE',
      backendStatus: 'RESPONSE_INVALID',
      backendResponse,
      attemptCount: 0,
    });
    expect((await service.resumePending()).resumed).toBe(0);
    expect((await service.retry(saved.editId))).toMatchObject({
      status: 'BACKEND_CONFIRMATION_INCOMPLETE',
      backendStatus: 'RESPONSE_INVALID',
    });
    expect(calls.value).toBe(0);
    const duplicate = await service.prepare(request);
    expect(duplicate).toMatchObject({
      editId: saved.editId,
      status: 'BACKEND_CONFIRMATION_INCOMPLETE',
      backendStatus: 'RESPONSE_INVALID',
    });
    service.close();
  });

  it('surfaces the unresolved confirmation to Electron and never repeats the backend route', async () => {
    const backendResponse = { ok: true, message: 'saved' };
    const bridge = {
      submit: vi.fn().mockResolvedValue({
        ok: false,
        saved: true,
        state: 'FAILED',
        status: 'BACKEND_CONFIRMATION_INCOMPLETE',
        editId: 'edit-1',
        backendStatus: 'RESPONSE_INVALID',
        backendHttpStatus: 200,
        backendResponse,
        backendError: 'backend success did not return a final event_id',
      }),
      backendSucceeded: vi.fn(),
      backendFailed: vi.fn(),
      retry: vi.fn(),
    };
    (globalThis as typeof globalThis & { localMappingBridge?: typeof bridge }).localMappingBridge = bridge;
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const result = await inspectorCommit({
      baseUrl: 'https://api.example.com',
      kind: 'structural_event',
      source: 'structural_bos',
      payload: { event_type: 'BOS_UP' },
    });

    expect(result).toMatchObject({
      ok: false,
      httpStatus: 200,
      error: 'backend success did not return a final event_id',
      localProcessing: {
        status: 'BACKEND_CONFIRMATION_INCOMPLETE',
        backendStatus: 'RESPONSE_INVALID',
      },
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(bridge.backendSucceeded).not.toHaveBeenCalled();
    expect(bridge.retry).not.toHaveBeenCalled();
  });
});
