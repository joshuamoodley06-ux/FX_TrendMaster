import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { afterEach, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { DatabaseSync } = require('node:sqlite');
const { createLocalMappingBridgeService, createLocalMappingStore, normalizeEditRequest } = require('../electron/localMappingBridge.cjs') as {
  createLocalMappingBridgeService: (options: Record<string, unknown>) => any;
  createLocalMappingStore: (options: Record<string, unknown>) => any;
  normalizeEditRequest: (request: Record<string, unknown>) => { editId: string };
};
const tempRoots: string[] = [];
function tempDb(name = 'range_library_memory.sqlite3'): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-local-bridge-v2-'));
  tempRoots.push(root);
  return path.join(root, name);
}
afterEach(() => { for (const root of tempRoots.splice(0)) fs.rmSync(root, { recursive: true, force: true }); });

function completingProcessor(counter: { value: number }) {
  return async ({ editId, databasePath }: { editId: string; databasePath: string }) => {
    counter.value += 1;
    const db = new DatabaseSync(databasePath);
    const now = new Date().toISOString();
    db.prepare(`UPDATE local_mapping_edits SET status='PROCESSED', attempt_count=attempt_count+1,
      result_json=?, processed_at_utc=?, updated_at_utc=?, python_database_path=? WHERE edit_id=?`)
      .run(JSON.stringify({ ok: true }), now, now, path.resolve(databasePath), editId);
    db.close();
    return { ok: true };
  };
}

describe('local mapping bridge two-phase durability', () => {
  it('gives an identical instruction one deterministic identity', () => {
    const request = { kind: 'structural_range', source: 'structural_range_save', payload: { symbol: 'XAUUSD', range_low: 2300, range_high: 2400 } };
    expect(normalizeEditRequest(request).editId).toBe(normalizeEditRequest(request).editId);
  });

  it('stores an instruction without invoking Python before backend confirmation', async () => {
    const databasePath = tempDb();
    const counter = { value: 0 };
    const service = createLocalMappingBridgeService({ databasePath, processor: completingProcessor(counter) });
    const saved = await service.prepare({ kind: 'structural_range', source: 'structural_range_save', payload: { symbol: 'XAUUSD' } });
    expect(saved).toMatchObject({ saved: true, status: 'AWAITING_BACKEND', backendStatus: 'UNCONFIRMED' });
    expect(counter.value).toBe(0);
    service.close();
  });

  it('preserves backend rejection without making the edit Python-retryable', async () => {
    const databasePath = tempDb();
    const counter = { value: 0 };
    const service = createLocalMappingBridgeService({ databasePath, processor: completingProcessor(counter) });
    const saved = await service.prepare({ kind: 'structural_event', source: 'structural_bos', payload: { event_type: 'BOS_UP' } });
    const rejected = service.backendFailed(saved.editId, { error: 'rejected', response: { ok: false }, httpStatus: 409 });
    expect(rejected).toMatchObject({ status: 'BACKEND_REJECTED', backendStatus: 'REJECTED', backendError: 'rejected' });
    expect((await service.resumePending()).resumed).toBe(0);
    expect(counter.value).toBe(0);
    service.close();
  });

  it('stores backend final identity before invoking Python', async () => {
    const databasePath = tempDb();
    const seen: Array<Record<string, unknown>> = [];
    const processor = async ({ editId, databasePath: dbPath }: { editId: string; databasePath: string }) => {
      const db = new DatabaseSync(dbPath);
      seen.push(db.prepare('SELECT backend_status, backend_range_id, backend_confirmed_payload_json FROM local_mapping_edits WHERE edit_id=?').get(editId));
      const now = new Date().toISOString();
      db.prepare("UPDATE local_mapping_edits SET status='PROCESSED',attempt_count=attempt_count+1,processed_at_utc=?,updated_at_utc=? WHERE edit_id=?").run(now, now, editId);
      db.close();
      return { ok: true };
    };
    const service = createLocalMappingBridgeService({ databasePath, processor });
    const saved = await service.prepare({ kind: 'structural_range', source: 'structural_range_save', payload: { case_ref: 'case-A', symbol: 'XAUUSD' } });
    await service.backendSucceeded(saved.editId, { ok: true, range_id: 42 }, 200);
    expect(seen[0]).toMatchObject({ backend_status: 'CONFIRMED', backend_range_id: '42' });
    expect(JSON.parse(String(seen[0].backend_confirmed_payload_json)).payload).toMatchObject({ backend_range_id: '42', source_record_id: '42' });
    service.close();
  });

  it('restarts after backend success and resumes Python exactly once', async () => {
    const databasePath = tempDb();
    const before = createLocalMappingStore({ databasePath });
    const saved = before.saveInstruction({ kind: 'structural_range', source: 'structural_range_save', payload: { case_ref: 'case-A', symbol: 'XAUUSD' } });
    before.recordBackendSuccess(saved.editId, { ok: true, range_id: 88 }, 200);
    before.close();

    const counter = { value: 0 };
    const service = createLocalMappingBridgeService({ databasePath, processor: completingProcessor(counter) });
    expect((await service.resumePending()).resumed).toBe(1);
    expect(counter.value).toBe(1);
    await service.retry(saved.editId);
    expect(counter.value).toBe(1);
    const duplicate = await service.prepare({ kind: 'structural_range', source: 'structural_range_save', payload: { case_ref: 'case-A', symbol: 'XAUUSD' } });
    expect(duplicate).toMatchObject({ editId: saved.editId, backendStatus: 'CONFIRMED', state: 'SUCCESS' });
    service.close();
  });
});
