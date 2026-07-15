/**
 * Typed renderer adapter for the persisted Python XAUUSD Master Map.
 *
 * The Python output owns hierarchy truth. This module only validates and
 * translates that output for Electron; it never rebuilds parent links from
 * source cases or raw mapping rows.
 */

export const MASTER_MAP_SCHEMA_VERSION = 'xauusd_master_map_v0.1' as const;

export type MasterMapHierarchyMode = 'trusted' | 'review' | 'all';
export type MasterMapLayer = 'WEEKLY' | 'DAILY' | 'INTRADAY';
export type MasterMapNavigationStatus = 'TRUSTED' | 'REVIEW' | 'HIDDEN';
export type MasterMapStatisticsStatus = 'ELIGIBLE' | 'EXCLUDED';

export type MasterMapSourceRef = {
  rawId: number | null;
  caseRef: string | null;
  sourceRecordId: string;
  payloadSha256: string | null;
};

export type MasterMapRangeNode = {
  canonicalRangeId: string;
  layer: MasterMapLayer;
  sourceTimeframe: string | null;
  rangeHigh: number | null;
  rangeLow: number | null;
  rangeHighTime: string | null;
  rangeLowTime: string | null;
  activeFromTime: string | null;
  inactiveFromTime: string | null;
  status: string;
  directionOfBreak: string | null;
  navigationStatus: MasterMapNavigationStatus;
  statisticsStatus: MasterMapStatisticsStatus;
  ancestorReviewStatus: string;
  directParentLinkStatus: string;
  reviewContextOnly: boolean;
  unlinkedReview: boolean;
  sourceCount: number;
  sourceRefs: MasterMapSourceRef[];
  children: MasterMapRangeNode[];
};

export type MasterMapSymbolNode = {
  canonicalRootId: string;
  symbol: 'XAUUSD';
  children: MasterMapRangeNode[];
  unlinkedReviewChildren: MasterMapRangeNode[];
};

export type MasterMapDocument = {
  schemaVersion: typeof MASTER_MAP_SCHEMA_VERSION;
  buildId: string;
  builtAtUtc: string;
  symbol: 'XAUUSD';
  structuralContentHash: string;
  trustedRoot: MasterMapSymbolNode;
  reviewRoot: MasterMapSymbolNode;
  allNavigationRoot: MasterMapSymbolNode;
  statistics: Record<string, unknown>;
};

export class MasterMapAdapterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MasterMapAdapterError';
  }
}

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown, path: string): UnknownRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new MasterMapAdapterError(`${path} must be an object.`);
  }
  return value as UnknownRecord;
}

function asArray(value: unknown, path: string): unknown[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new MasterMapAdapterError(`${path} must be an array.`);
  }
  return value;
}

function requiredString(value: unknown, path: string): string {
  const result = String(value ?? '').trim();
  if (!result) throw new MasterMapAdapterError(`${path} is required.`);
  return result;
}

function optionalString(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const result = String(value).trim();
  return result || null;
}

function optionalNumber(value: unknown, path: string): number | null {
  if (value === undefined || value === null || value === '') return null;
  const result = Number(value);
  if (!Number.isFinite(result)) {
    throw new MasterMapAdapterError(`${path} must be a finite number or null.`);
  }
  return result;
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  const result = requiredString(value, path).toUpperCase() as T;
  if (!allowed.includes(result)) {
    throw new MasterMapAdapterError(`${path} has unsupported value ${result}.`);
  }
  return result;
}

function adaptSourceRef(value: unknown, path: string): MasterMapSourceRef {
  const row = asRecord(value, path);
  const rawIdValue = row.raw_id;
  const rawId = rawIdValue === undefined || rawIdValue === null
    ? null
    : optionalNumber(rawIdValue, `${path}.raw_id`);
  return {
    rawId,
    caseRef: optionalString(row.case_ref),
    sourceRecordId: requiredString(row.source_record_id, `${path}.source_record_id`),
    payloadSha256: optionalString(row.payload_sha256),
  };
}

function adaptRangeNode(value: unknown, path: string, unlinkedReview = false): MasterMapRangeNode {
  const row = asRecord(value, path);
  const nodeType = requiredString(row.node_type, `${path}.node_type`).toUpperCase();
  if (nodeType !== 'RANGE') {
    throw new MasterMapAdapterError(`${path}.node_type must be RANGE.`);
  }
  const navigationStatus = enumValue(
    row.navigation_status,
    ['TRUSTED', 'REVIEW', 'HIDDEN'] as const,
    `${path}.navigation_status`,
  );
  const statisticsStatus = enumValue(
    row.statistics_status,
    ['ELIGIBLE', 'EXCLUDED'] as const,
    `${path}.statistics_status`,
  );
  if (navigationStatus === 'REVIEW' && statisticsStatus !== 'EXCLUDED') {
    throw new MasterMapAdapterError(`${path} is REVIEW navigation and must be EXCLUDED from statistics.`);
  }

  const sourceRefs = asArray(row.source_refs, `${path}.source_refs`)
    .map((item, index) => adaptSourceRef(item, `${path}.source_refs[${index}]`));
  const children = asArray(row.children, `${path}.children`)
    .map((item, index) => adaptRangeNode(item, `${path}.children[${index}]`));

  return {
    canonicalRangeId: requiredString(row.id, `${path}.id`),
    layer: enumValue(
      row.structure_layer,
      ['WEEKLY', 'DAILY', 'INTRADAY'] as const,
      `${path}.structure_layer`,
    ),
    sourceTimeframe: optionalString(row.source_timeframe)?.toUpperCase() ?? null,
    rangeHigh: optionalNumber(row.range_high, `${path}.range_high`),
    rangeLow: optionalNumber(row.range_low, `${path}.range_low`),
    rangeHighTime: optionalString(row.range_high_time),
    rangeLowTime: optionalString(row.range_low_time),
    activeFromTime: optionalString(row.active_from_time),
    inactiveFromTime: optionalString(row.inactive_from_time),
    status: requiredString(row.status, `${path}.status`).toUpperCase(),
    directionOfBreak: optionalString(row.direction_of_break)?.toUpperCase() ?? null,
    navigationStatus,
    statisticsStatus,
    ancestorReviewStatus: requiredString(
      row.ancestor_review_status,
      `${path}.ancestor_review_status`,
    ).toUpperCase(),
    directParentLinkStatus: requiredString(
      row.direct_parent_link_status,
      `${path}.direct_parent_link_status`,
    ).toUpperCase(),
    reviewContextOnly: row.review_context_only === true,
    unlinkedReview,
    sourceCount: optionalNumber(row.source_count, `${path}.source_count`) ?? sourceRefs.length,
    sourceRefs,
    children,
  };
}

function adaptSymbolRoot(value: unknown, path: string): MasterMapSymbolNode {
  const row = asRecord(value, path);
  const nodeType = requiredString(row.node_type, `${path}.node_type`).toUpperCase();
  if (nodeType !== 'SYMBOL') {
    throw new MasterMapAdapterError(`${path}.node_type must be SYMBOL.`);
  }
  const symbol = requiredString(row.label, `${path}.label`).toUpperCase();
  if (symbol !== 'XAUUSD') {
    throw new MasterMapAdapterError(`${path}.label must be XAUUSD.`);
  }
  return {
    canonicalRootId: requiredString(row.id, `${path}.id`),
    symbol,
    children: asArray(row.children, `${path}.children`)
      .map((item, index) => adaptRangeNode(item, `${path}.children[${index}]`)),
    unlinkedReviewChildren: asArray(
      row.unlinked_review_children,
      `${path}.unlinked_review_children`,
    ).map((item, index) => adaptRangeNode(
      item,
      `${path}.unlinked_review_children[${index}]`,
      true,
    )),
  };
}

function walkRoot(root: MasterMapSymbolNode, visit: (node: MasterMapRangeNode) => void): void {
  const stack = [...root.children, ...root.unlinkedReviewChildren];
  while (stack.length) {
    const node = stack.pop() as MasterMapRangeNode;
    visit(node);
    stack.push(...node.children);
  }
}

function assertRootContracts(document: MasterMapDocument): void {
  walkRoot(document.trustedRoot, (node) => {
    if (node.navigationStatus !== 'TRUSTED' || node.statisticsStatus !== 'ELIGIBLE') {
      throw new MasterMapAdapterError(
        `trusted_root contains non-trusted range ${node.canonicalRangeId}.`,
      );
    }
  });
  walkRoot(document.reviewRoot, (node) => {
    const isReviewNode = node.navigationStatus === 'REVIEW';
    if (!isReviewNode && !node.reviewContextOnly) {
      throw new MasterMapAdapterError(
        `review_root contains non-review range ${node.canonicalRangeId} without review context.`,
      );
    }
    if (isReviewNode && node.statisticsStatus !== 'EXCLUDED') {
      throw new MasterMapAdapterError(
        `review range ${node.canonicalRangeId} must be excluded from statistics.`,
      );
    }
  });
  walkRoot(document.allNavigationRoot, (node) => {
    if (node.navigationStatus === 'HIDDEN') {
      throw new MasterMapAdapterError(
        `root contains hidden range ${node.canonicalRangeId}; hidden rows are not navigable.`,
      );
    }
    if (node.navigationStatus === 'REVIEW' && node.statisticsStatus !== 'EXCLUDED') {
      throw new MasterMapAdapterError(
        `review range ${node.canonicalRangeId} must be excluded from statistics.`,
      );
    }
  });
}

export function adaptMasterMapOutput(value: unknown): MasterMapDocument {
  const row = asRecord(value, 'master_map');
  const schemaVersion = requiredString(row.schema_version, 'master_map.schema_version');
  if (schemaVersion !== MASTER_MAP_SCHEMA_VERSION) {
    throw new MasterMapAdapterError(`Unsupported Master Map schema ${schemaVersion}.`);
  }
  const symbol = requiredString(row.symbol, 'master_map.symbol').toUpperCase();
  if (symbol !== 'XAUUSD') {
    throw new MasterMapAdapterError('Master Map v0.1 is scoped to XAUUSD only.');
  }
  const statistics = asRecord(row.statistics, 'master_map.statistics');
  const document: MasterMapDocument = {
    schemaVersion: MASTER_MAP_SCHEMA_VERSION,
    buildId: requiredString(row.build_id, 'master_map.build_id'),
    builtAtUtc: requiredString(row.built_at_utc, 'master_map.built_at_utc'),
    symbol,
    structuralContentHash: requiredString(
      row.structural_content_hash,
      'master_map.structural_content_hash',
    ),
    trustedRoot: adaptSymbolRoot(row.trusted_root, 'master_map.trusted_root'),
    reviewRoot: adaptSymbolRoot(row.review_root, 'master_map.review_root'),
    allNavigationRoot: adaptSymbolRoot(row.root, 'master_map.root'),
    statistics: { ...statistics },
  };
  assertRootContracts(document);
  return document;
}

/**
 * Selects only the Python-owned root for the explicit hierarchy mode.
 * `root` is never a fallback for normal or review navigation.
 */
export function masterMapRootForMode(
  document: MasterMapDocument,
  mode: MasterMapHierarchyMode,
): MasterMapSymbolNode {
  if (mode === 'review') return document.reviewRoot;
  if (mode === 'all') return document.allNavigationRoot;
  return document.trustedRoot;
}

export function flattenMasterMapRanges(root: MasterMapSymbolNode): MasterMapRangeNode[] {
  const result: MasterMapRangeNode[] = [];
  walkRoot(root, (node) => result.push(node));
  return result;
}
