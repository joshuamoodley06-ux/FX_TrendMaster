import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { afterEach, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { DatabaseSync } = require('node:sqlite');
const {
  createLocalMappingBridgeService,
  createLocalMappingStore,
  normalizeEditRequest,
} = require('../electron/localMappingBridge.cjs') as {
  createLocalMappingBridgeService: (options: Record<string, unknown>) => any;
  createLocalMappingStore: (options: Record<string, unknown>) => any;
  normalizeEditRequest: (request: Record<string, unknown>) => { editId: string };
};

const tempRoots: string[] = [];

function tempDb(name = 'range_library_memory.sqlite3'): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-local-bridge-'));
  tempRoots.push(root);
  return path.join(root, name);
}

afterEach(() => {
  for (const root of tempRoots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe('local mapping bridge', () => {
  it('gives the same confirmed action one deterministic edit identity', () => {
    const request = {
      kind: 'structural_range',
      source: 'structural_range_save',
      payload: { symbol: 'XAUUSD', range_low: 2300, range_high: 2400 },
    };
    expect(normalizeEditRequest(request).editId).toBe(normalizeEditRequest(request).editId);
  });

  it('persists before processing and exact retry cannot create a duplicate', async () => {
    const databasePath = tempDb();
    const processor = async ({ editId, databasePath: dbPath }: { editId: string; databasePath: string }) => {
      const db = new DatabaseSync(dbPath);
      const result = { ok: true, edit_id: editId, database_path: path.resolve(dbPath) };
      db.prepare(`
        UPDATE local_mapping_edits
        SET status='PROCESSED', attempt_count=attempt_count+1,
            result_json=?, processed_at_utc=?, updated_at_utc=?,
            processor_version='test', python_database_path=?
        WHERE edit_id=?
      `).run(
        JSON.stringify(result),
        new Date().toISOString(),
        new Date().toISOString(),
        path.resolve(dbPath),
        editId,
      );
      db.close();
      return { ok: true, parsed: result };
    };
    const service = createLocalMappingBridgeService({ databasePath, processor });
    const request = {
      kind: 'structural_range',
      source: 'structural_range_save',
      payload: { id: 'range-1', range_high: 2400, range_low: 2300 },
    };

    const first = await service.submit(request);
    const second = await service.submit(request);

    expect(first).toMatchObject({ state: 'SUCCESS', saved: true, sameDatabasePath: true });
    expect(second).toMatchObject({ state: 'SUCCESS', saved: true });
    expect(service.store.count()).toBe(1);
    service.close();
  });

  it('survives close and reopen with processing state intact', async () => {
    const databasePath = tempDb();
    const service = createLocalMappingBridgeService({
      databasePath,
      processor: async () => ({ ok: false, error: 'synthetic processor failure' }),
    });
    const failed = await service.submit({
      kind: 'structural_event',
      source: 'structural_bos',
      payload: { event_id: 'event-1', event_type: 'BOS_UP' },
    });
    service.close();

    const reopened = createLocalMappingStore({ databasePath });
    expect(reopened.count()).toBe(1);
    expect(reopened.getStatus(failed.editId)).toMatchObject({
      state: 'FAILED',
      saved: true,
      error: 'synthetic processor failure',
    });
    reopened.close();
  });

  it('recovers an interrupted PROCESSING edit as PENDING after restart', () => {
    const databasePath = tempDb();
    const store = createLocalMappingStore({ databasePath });
    const saved = store.save({
      kind: 'structural_event',
      source: 'structural_bos',
      payload: { event_id: 'event-2' },
    });
    const db = new DatabaseSync(databasePath);
    db.prepare("UPDATE local_mapping_edits SET status='PROCESSING' WHERE edit_id=?").run(saved.editId);
    db.close();
    store.close();

    const reopened = createLocalMappingStore({ databasePath });
    expect(reopened.recoverInterrupted()).toBe(1);
    expect(reopened.getStatus(saved.editId)).toMatchObject({ state: 'PENDING', saved: true });
    reopened.close();
  });
});
