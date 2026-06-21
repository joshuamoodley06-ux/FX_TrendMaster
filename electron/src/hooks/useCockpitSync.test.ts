import { describe, expect, it } from 'vitest';
import { COCKPIT_SYNC_AUTO_POLL_ENABLED } from '../cockpitSyncService';

describe('cockpitSyncService', () => {
  it('disables background polling for this session', () => {
    expect(COCKPIT_SYNC_AUTO_POLL_ENABLED).toBe(false);
  });
});
