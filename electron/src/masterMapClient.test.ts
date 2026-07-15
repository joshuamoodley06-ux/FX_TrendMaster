import { describe, expect, it, vi } from 'vitest';
import { loadPersistedMasterMap, type MasterMapBridge } from './masterMapClient';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('masterMapClient', () => {
  it('loads and adapts the persisted map through the injected Electron bridge', async () => {
    const bridge: MasterMapBridge = {
      getMasterMap: vi.fn().mockResolvedValue({
        ok: true,
        databasePath: 'range_library_memory.sqlite3',
        masterMap: masterMapFixture(),
      }),
    };

    const result = await loadPersistedMasterMap('XAUUSD', bridge);

    expect(bridge.getMasterMap).toHaveBeenCalledWith('XAUUSD');
    expect(result).toMatchObject({
      ok: true,
      document: {
        symbol: 'XAUUSD',
        trustedRoot: { canonicalRootId: 'symbol:XAUUSD:trusted' },
      },
    });
  });

  it('reports a missing Electron bridge without attempting another data source', async () => {
    await expect(loadPersistedMasterMap('XAUUSD', null)).resolves.toMatchObject({
      ok: false,
      document: null,
      error: expect.stringContaining('bridge unavailable'),
    });
  });

  it('surfaces persisted schema failures as a load error', async () => {
    const bridge: MasterMapBridge = {
      getMasterMap: vi.fn().mockResolvedValue({
        ok: true,
        databasePath: 'range_library_memory.sqlite3',
        masterMap: { ...masterMapFixture(), schema_version: 'future_schema' },
      }),
    };

    await expect(loadPersistedMasterMap('XAUUSD', bridge)).resolves.toMatchObject({
      ok: false,
      document: null,
      error: expect.stringContaining('Unsupported Master Map schema'),
    });
  });
});
