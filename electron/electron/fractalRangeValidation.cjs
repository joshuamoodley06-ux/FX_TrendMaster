/** Fractal range metadata — origin tracking only (no overlap validation). */

function resolveParentId(range) {
  const raw = range?.parent_id ?? range?.parentId ?? range?.parent_range_id ?? null;
  if (raw == null || raw === '') return null;
  return String(raw).trim() || null;
}

function validateFractalRange(candidate) {
  const high = Number(candidate?.range_high ?? candidate?.rangeHigh);
  const low = Number(candidate?.range_low ?? candidate?.rangeLow);
  if (!Number.isFinite(high) || !Number.isFinite(low)) {
    return {
      is_valid: false,
      origin: null,
      flags: ['invalid_bounds'],
      reason: 'range_high and range_low are required numbers',
    };
  }

  const parentId = resolveParentId(candidate);
  const origin = parentId ? 'Child' : 'Root';
  const flags = parentId ? [] : ['root'];

  return {
    is_valid: true,
    origin,
    flags,
    reason: null,
  };
}

module.exports = {
  validateFractalRange,
  resolveParentId,
};
