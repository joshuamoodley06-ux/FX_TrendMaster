type NodeOptions = {
  navigation?: 'TRUSTED' | 'REVIEW';
  statistics?: 'ELIGIBLE' | 'EXCLUDED';
  children?: Record<string, unknown>[];
  reviewContextOnly?: boolean;
  direction?: 'UP' | 'DOWN' | null;
  status?: string;
  caseRef?: string;
  script1?: {
    chronology: 'RL_TO_RH' | 'RH_TO_RL' | 'PENDING';
    direction: 'BOS_UP' | 'BOS_DOWN' | 'PENDING';
    time?: string | null;
    status: 'COMPLETE' | 'PENDING' | 'NEEDS_REVIEW';
    reasons?: string[];
  };
};

function sourceRef(sourceRecordId: string, caseRef = 'case:live') {
  return {
    raw_id: Number(sourceRecordId.replace(/\D/g, '')) || 1,
    case_ref: caseRef,
    source_record_id: sourceRecordId,
    payload_sha256: `sha-${sourceRecordId}`,
  };
}

function rangeNode(
  id: string,
  layer: 'WEEKLY' | 'DAILY' | 'INTRADAY',
  options: NodeOptions = {},
): Record<string, unknown> {
  const navigation = options.navigation || 'TRUSTED';
  const statistics = options.statistics || (navigation === 'TRUSTED' ? 'ELIGIBLE' : 'EXCLUDED');
  const sourceTimeframe = layer === 'WEEKLY' ? 'W1' : layer === 'DAILY' ? 'D1' : 'H4';
  const priceOffset = layer === 'WEEKLY' ? 300 : layer === 'DAILY' ? 200 : 100;
  const result: Record<string, unknown> = {
    id,
    node_type: 'RANGE',
    structure_layer: layer,
    source_timeframe: sourceTimeframe,
    range_high: 2500 + priceOffset,
    range_low: 2000 + priceOffset,
    range_high_time: '2026-01-04T00:00:00Z',
    range_low_time: '2026-01-01T00:00:00Z',
    active_from_time: '2026-01-04T00:00:00Z',
    inactive_from_time: options.status === 'BROKEN' ? '2026-03-01T00:00:00Z' : null,
    status: options.status || 'ACTIVE',
    direction_of_break: options.direction ?? null,
    source_count: 1,
    source_refs: [sourceRef(id, options.caseRef)],
    navigation_status: navigation,
    statistics_status: statistics,
    ancestor_review_status: navigation === 'TRUSTED' ? 'CLEAR' : 'SELF_NEEDS_REVIEW',
    direct_parent_link_status: layer === 'WEEKLY' ? 'ROOT' : 'VALID',
    review_context_only: options.reviewContextOnly === true,
    events: [],
    children: options.children || [],
  };
  if (options.script1) {
    result.script1_chronology = options.script1.chronology;
    result.script1_bos_direction = options.script1.direction;
    result.script1_bos_time = options.script1.time ?? null;
    result.script1_processing_status = options.script1.status;
    result.script1_reason_codes = options.script1.reasons || [];
  }
  return result;
}

export function masterMapFixture(): Record<string, unknown> {
  const trustedIntraday = rangeNode('mm:range:intraday-trusted', 'INTRADAY');
  const trustedDaily = rangeNode('mm:range:daily-trusted', 'DAILY', {
    children: [trustedIntraday],
  });
  const trustedWeekly = rangeNode('mm:range:weekly-trusted', 'WEEKLY', {
    status: 'BROKEN',
    direction: 'DOWN',
    children: [trustedDaily],
    script1: {
      chronology: 'RL_TO_RH',
      direction: 'BOS_UP',
      time: '2026-02-01T00:00:00Z',
      status: 'COMPLETE',
    },
  });

  const reviewIntraday = rangeNode('mm:range:intraday-review', 'INTRADAY', {
    navigation: 'REVIEW',
    statistics: 'EXCLUDED',
    caseRef: 'case:old-copy',
  });
  const reviewDaily = rangeNode('mm:range:daily-review', 'DAILY', {
    navigation: 'REVIEW',
    statistics: 'EXCLUDED',
    children: [reviewIntraday],
    caseRef: 'case:old-copy',
  });
  const reviewWeeklyContext = rangeNode('mm:range:weekly-trusted', 'WEEKLY', {
    status: 'BROKEN',
    direction: 'DOWN',
    reviewContextOnly: true,
    children: [reviewDaily],
  });
  const unlinkedReview = rangeNode('mm:range:daily-unlinked-review', 'DAILY', {
    navigation: 'REVIEW',
    statistics: 'EXCLUDED',
    caseRef: 'case:orphan',
  });
  const allWeekly = rangeNode('mm:range:weekly-trusted', 'WEEKLY', {
    status: 'BROKEN',
    direction: 'DOWN',
    children: [trustedDaily, reviewDaily],
  });

  return {
    schema_version: 'xauusd_master_map_v0.1',
    build_id: 'fixture-build',
    built_at_utc: '2026-07-13T00:00:00Z',
    symbol: 'XAUUSD',
    structural_content_hash: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    trusted_root: {
      id: 'symbol:XAUUSD:trusted',
      node_type: 'SYMBOL',
      label: 'XAUUSD',
      children: [trustedWeekly],
    },
    review_root: {
      id: 'symbol:XAUUSD:review',
      node_type: 'SYMBOL',
      label: 'XAUUSD',
      children: [reviewWeeklyContext],
      unlinked_review_children: [unlinkedReview],
    },
    root: {
      id: 'symbol:XAUUSD',
      node_type: 'SYMBOL',
      label: 'XAUUSD',
      children: [allWeekly],
      unlinked_review_children: [unlinkedReview],
    },
    statistics: {
      comparison_eligible_ranges: 3,
      review_visible_ranges_by_layer: { WEEKLY: 0, DAILY: 2, INTRADAY: 1 },
    },
    review_items: [],
    lifecycle_evidence_report: [],
  };
}
