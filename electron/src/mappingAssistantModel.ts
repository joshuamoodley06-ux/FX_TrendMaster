import type { MappingGap } from './mappingWorkflow';
import {
  adaptMasterMapOutput,
  flattenMasterMapRanges,
  type MasterMapDocument,
  type MasterMapLayer,
  type MasterMapRangeNode,
} from './masterMapAdapter';
import type { MasterMapNavigationRequest } from './masterMapHierarchy';

export const MAPPING_ASSISTANT_SCHEMA_VERSION = 'xauusd_mapping_assistant_snapshot_v0.1' as const;
export const MAPPING_ASSISTANT_GAP_SCHEMA_VERSION = 'xauusd_mapping_assistant_gap_v0.1' as const;

export type MappingAssistantNavigationTarget = {
  canonicalRangeId: string;
  eventId: string | null;
  targetLayer: MasterMapLayer;
  targetTimeframe: string;
  preferredAnchorTime: string | null;
  visibleStart: string | null;
  visibleEnd: string | null;
};

export type MappingAssistantParent = {
  canonicalRangeId: string;
  sourceRangeIds: string[];
  structureLayer: MasterMapLayer;
  sourceTimeframe: string;
  rangeHigh: number;
  rangeLow: number;
  rangeHighTime: string;
  rangeLowTime: string;
  activeFromTime: string;
  inactiveFromTime: string | null;
  status: string;
  navigationStatus: string;
  statisticsStatus: string;
  sourceRefs: unknown[];
};

export type MappingAssistantResearchGap = {
  schemaVersion: typeof MAPPING_ASSISTANT_GAP_SCHEMA_VERSION;
  gapId: string;
  priorityRank: number;
  gapType: 'RESEARCH_EVIDENCE';
  symbol: 'XAUUSD';
  parent: MappingAssistantParent;
  researchImpact: {
    blockedCandidateCount: number;
    blockedCandidateIds: string[];
    earliestCandidateFreeze: string | null;
    latestCandidateFreeze: string | null;
  };
  requirement: {
    missingEvidenceCode: string[];
    recommendedActionCode: string;
    evidenceAlreadyPresent: string[];
    traderTitle: string;
    traderInstruction: string;
  };
  navigation: {
    openStructure: MappingAssistantNavigationTarget;
    showFirstCandidate: MappingAssistantNavigationTarget;
  };
};

export type MappingAssistantSnapshot = {
  schemaVersion: typeof MAPPING_ASSISTANT_SCHEMA_VERSION;
  generatedAtUtc: string;
  symbol: 'XAUUSD';
  structuralContentHash: string;
  summary: {
    researchGapCount: number;
    blockedCandidateCount: number;
    uniqueWeeklyParentCount: number;
    structureQueryReadyCount: number;
    confirmationQueryReadyCount: number;
    outcomeQueryReadyCount: number;
    overallFirstQueryReadyCount: number;
  };
  gaps: MappingAssistantResearchGap[];
  masterMap: MasterMapDocument;
  determinismHash: string;
  sourceIntegrity: {
    databasePath: string;
    sha256Before: string;
    sha256After: string;
    unchanged: boolean;
    buildMode: string;
  };
};

export class MappingAssistantAdapterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MappingAssistantAdapterError';
  }
}

type UnknownRecord = Record<string, unknown>;

function record(value: unknown, path: string): UnknownRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new MappingAssistantAdapterError(`${path} must be an object.`);
  }
  return value as UnknownRecord;
}

function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new MappingAssistantAdapterError(`${path} must be an array.`);
  return value;
}

function text(value: unknown, path: string): string {
  const result = String(value ?? '').trim();
  if (!result) throw new MappingAssistantAdapterError(`${path} is required.`);
  return result;
}

function optionalText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const result = String(value).trim();
  return result || null;
}

function finite(value: unknown, path: string): number {
  const result = Number(value);
  if (!Number.isFinite(result)) throw new MappingAssistantAdapterError(`${path} must be a finite number.`);
  return result;
}

function nonNegativeInteger(value: unknown, path: string): number {
  const result = finite(value, path);
  if (!Number.isInteger(result) || result < 0) {
    throw new MappingAssistantAdapterError(`${path} must be a non-negative integer.`);
  }
  return result;
}

function stringArray(value: unknown, path: string): string[] {
  return array(value, path).map((item, index) => text(item, `${path}[${index}]`));
}

function layer(value: unknown, path: string): MasterMapLayer {
  const result = text(value, path).toUpperCase();
  if (!['WEEKLY', 'DAILY', 'INTRADAY'].includes(result)) {
    throw new MappingAssistantAdapterError(`${path} has unsupported layer ${result}.`);
  }
  return result as MasterMapLayer;
}

function navigationTarget(value: unknown, path: string): MappingAssistantNavigationTarget {
  const row = record(value, path);
  return {
    canonicalRangeId: text(row.canonical_range_id, `${path}.canonical_range_id`),
    eventId: optionalText(row.event_id),
    targetLayer: layer(row.target_layer, `${path}.target_layer`),
    targetTimeframe: text(row.target_timeframe, `${path}.target_timeframe`).toUpperCase(),
    preferredAnchorTime: optionalText(row.preferred_anchor_time),
    visibleStart: optionalText(row.visible_start),
    visibleEnd: optionalText(row.visible_end),
  };
}

function adaptParent(value: unknown, path: string): MappingAssistantParent {
  const row = record(value, path);
  const high = finite(row.range_high, `${path}.range_high`);
  const low = finite(row.range_low, `${path}.range_low`);
  if (high <= low) throw new MappingAssistantAdapterError(`${path} range high must exceed range low.`);
  return {
    canonicalRangeId: text(row.canonical_range_id, `${path}.canonical_range_id`),
    sourceRangeIds: stringArray(row.source_range_ids ?? [], `${path}.source_range_ids`),
    structureLayer: layer(row.structure_layer, `${path}.structure_layer`),
    sourceTimeframe: text(row.source_timeframe, `${path}.source_timeframe`).toUpperCase(),
    rangeHigh: high,
    rangeLow: low,
    rangeHighTime: text(row.range_high_time, `${path}.range_high_time`),
    rangeLowTime: text(row.range_low_time, `${path}.range_low_time`),
    activeFromTime: text(row.active_from_time, `${path}.active_from_time`),
    inactiveFromTime: optionalText(row.inactive_from_time),
    status: text(row.status, `${path}.status`).toUpperCase(),
    navigationStatus: text(row.navigation_status, `${path}.navigation_status`).toUpperCase(),
    statisticsStatus: text(row.statistics_status, `${path}.statistics_status`).toUpperCase(),
    sourceRefs: array(row.source_refs ?? [], `${path}.source_refs`),
  };
}

function adaptGap(value: unknown, path: string): MappingAssistantResearchGap {
  const row = record(value, path);
  const schemaVersion = text(row.schema_version, `${path}.schema_version`);
  if (schemaVersion !== MAPPING_ASSISTANT_GAP_SCHEMA_VERSION) {
    throw new MappingAssistantAdapterError(`${path} has unsupported schema ${schemaVersion}.`);
  }
  if (text(row.gap_type, `${path}.gap_type`).toUpperCase() !== 'RESEARCH_EVIDENCE') {
    throw new MappingAssistantAdapterError(`${path}.gap_type must be RESEARCH_EVIDENCE.`);
  }
  const symbol = text(row.symbol, `${path}.symbol`).toUpperCase();
  if (symbol !== 'XAUUSD') throw new MappingAssistantAdapterError(`${path}.symbol must be XAUUSD.`);
  const impact = record(row.research_impact, `${path}.research_impact`);
  const requirement = record(row.requirement, `${path}.requirement`);
  const navigation = record(row.navigation, `${path}.navigation`);
  return {
    schemaVersion: MAPPING_ASSISTANT_GAP_SCHEMA_VERSION,
    gapId: text(row.gap_id, `${path}.gap_id`),
    priorityRank: nonNegativeInteger(row.priority_rank, `${path}.priority_rank`),
    gapType: 'RESEARCH_EVIDENCE',
    symbol: 'XAUUSD',
    parent: adaptParent(row.parent, `${path}.parent`),
    researchImpact: {
      blockedCandidateCount: nonNegativeInteger(
        impact.blocked_candidate_count,
        `${path}.research_impact.blocked_candidate_count`,
      ),
      blockedCandidateIds: stringArray(
        impact.blocked_candidate_ids ?? [],
        `${path}.research_impact.blocked_candidate_ids`,
      ),
      earliestCandidateFreeze: optionalText(impact.earliest_candidate_freeze),
      latestCandidateFreeze: optionalText(impact.latest_candidate_freeze),
    },
    requirement: {
      missingEvidenceCode: stringArray(
        requirement.missing_evidence_code ?? [],
        `${path}.requirement.missing_evidence_code`,
      ),
      recommendedActionCode: text(
        requirement.recommended_action_code,
        `${path}.requirement.recommended_action_code`,
      ),
      evidenceAlreadyPresent: stringArray(
        requirement.evidence_already_present ?? [],
        `${path}.requirement.evidence_already_present`,
      ),
      traderTitle: text(requirement.trader_title, `${path}.requirement.trader_title`),
      traderInstruction: text(requirement.trader_instruction, `${path}.requirement.trader_instruction`),
    },
    navigation: {
      openStructure: navigationTarget(navigation.open_structure, `${path}.navigation.open_structure`),
      showFirstCandidate: navigationTarget(
        navigation.show_first_candidate,
        `${path}.navigation.show_first_candidate`,
      ),
    },
  };
}

export function adaptMappingAssistantSnapshot(value: unknown): MappingAssistantSnapshot {
  const row = record(value, 'mapping_assistant');
  const schemaVersion = text(row.schema_version, 'mapping_assistant.schema_version');
  if (schemaVersion !== MAPPING_ASSISTANT_SCHEMA_VERSION) {
    throw new MappingAssistantAdapterError(`Unsupported Mapping Assistant schema ${schemaVersion}.`);
  }
  const symbol = text(row.symbol, 'mapping_assistant.symbol').toUpperCase();
  if (symbol !== 'XAUUSD') throw new MappingAssistantAdapterError('Mapping Assistant v0.1 is XAUUSD only.');
  const summary = record(row.summary, 'mapping_assistant.summary');
  const integrity = record(row.source_integrity, 'mapping_assistant.source_integrity');
  const gaps = array(row.gaps, 'mapping_assistant.gaps')
    .map((item, index) => adaptGap(item, `mapping_assistant.gaps[${index}]`));
  const researchGapCount = nonNegativeInteger(summary.research_gap_count, 'mapping_assistant.summary.research_gap_count');
  if (researchGapCount !== gaps.length) {
    throw new MappingAssistantAdapterError('Mapping Assistant research gap count does not match gap rows.');
  }
  if (integrity.unchanged !== true || integrity.sha256_before !== integrity.sha256_after) {
    throw new MappingAssistantAdapterError('Mapping Assistant source integrity check failed.');
  }
  return {
    schemaVersion: MAPPING_ASSISTANT_SCHEMA_VERSION,
    generatedAtUtc: text(row.generated_at_utc, 'mapping_assistant.generated_at_utc'),
    symbol: 'XAUUSD',
    structuralContentHash: text(row.structural_content_hash, 'mapping_assistant.structural_content_hash'),
    summary: {
      researchGapCount,
      blockedCandidateCount: nonNegativeInteger(summary.blocked_candidate_count, 'mapping_assistant.summary.blocked_candidate_count'),
      uniqueWeeklyParentCount: nonNegativeInteger(summary.unique_weekly_parent_count, 'mapping_assistant.summary.unique_weekly_parent_count'),
      structureQueryReadyCount: nonNegativeInteger(summary.structure_query_ready_count, 'mapping_assistant.summary.structure_query_ready_count'),
      confirmationQueryReadyCount: nonNegativeInteger(summary.confirmation_query_ready_count, 'mapping_assistant.summary.confirmation_query_ready_count'),
      outcomeQueryReadyCount: nonNegativeInteger(summary.outcome_query_ready_count, 'mapping_assistant.summary.outcome_query_ready_count'),
      overallFirstQueryReadyCount: nonNegativeInteger(summary.overall_first_query_ready_count, 'mapping_assistant.summary.overall_first_query_ready_count'),
    },
    gaps,
    masterMap: adaptMasterMapOutput(row.master_map),
    determinismHash: text(row.determinism_hash, 'mapping_assistant.determinism_hash'),
    sourceIntegrity: {
      databasePath: text(integrity.database_path, 'mapping_assistant.source_integrity.database_path'),
      sha256Before: text(integrity.sha256_before, 'mapping_assistant.source_integrity.sha256_before'),
      sha256After: text(integrity.sha256_after, 'mapping_assistant.source_integrity.sha256_after'),
      unchanged: true,
      buildMode: text(integrity.build_mode, 'mapping_assistant.source_integrity.build_mode'),
    },
  };
}

export function masterMapNodeIndex(document: MasterMapDocument): Map<string, MasterMapRangeNode> {
  return new Map(
    flattenMasterMapRanges(document.allNavigationRoot)
      .map((node) => [node.canonicalRangeId, node] as const),
  );
}

export function navigationRequestForAssistantTarget(
  target: MappingAssistantNavigationTarget,
  document: MasterMapDocument,
): MasterMapNavigationRequest | null {
  const node = masterMapNodeIndex(document).get(target.canonicalRangeId);
  if (!node) return null;
  return {
    canonicalRangeId: target.canonicalRangeId,
    layer: target.targetLayer,
    sourceTimeframe: target.targetTimeframe,
    mode: 'all',
    range: node,
    reason: 'GAP',
    eventId: target.eventId,
    preferredAnchorTime: target.preferredAnchorTime,
    visibleStart: target.visibleStart,
    visibleEnd: target.visibleEnd,
  };
}

export function masterMapDocumentToCoverageRanges(document: MasterMapDocument): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  const visit = (node: MasterMapRangeNode, parentId: string | null) => {
    rows.push({
      range_id: node.canonicalRangeId,
      id: node.canonicalRangeId,
      canonical_range_id: node.canonicalRangeId,
      symbol: document.symbol,
      structure_layer: node.layer,
      layer: node.layer,
      source_timeframe: node.sourceTimeframe,
      chart_timeframe: node.sourceTimeframe,
      range_scope: 'MAJOR',
      range_high_price: node.rangeHigh,
      range_high: node.rangeHigh,
      range_low_price: node.rangeLow,
      range_low: node.rangeLow,
      range_high_time: node.rangeHighTime,
      range_low_time: node.rangeLowTime,
      range_start_time: node.activeFromTime || node.rangeHighTime || node.rangeLowTime,
      range_end_time: node.inactiveFromTime || node.rangeLowTime || node.rangeHighTime,
      active_from_time: node.activeFromTime,
      inactive_from_time: node.inactiveFromTime,
      status: node.status,
      parent_range_id: parentId,
      navigation_status: node.navigationStatus,
      statistics_status: node.statisticsStatus,
      source_refs: node.sourceRefs,
    });
    node.children.forEach((child) => visit(child, node.canonicalRangeId));
  };
  document.allNavigationRoot.children.forEach((node) => visit(node, null));
  document.allNavigationRoot.unlinkedReviewChildren.forEach((node) => visit(node, null));
  return rows;
}

export function navigationRequestForCoverageGap(
  gap: MappingGap,
  document: MasterMapDocument,
): MasterMapNavigationRequest | null {
  const node = masterMapNodeIndex(document).get(gap.parentId);
  if (!node || !['WEEKLY', 'DAILY', 'INTRADAY'].includes(gap.expectedChildLayer)) return null;
  return {
    canonicalRangeId: node.canonicalRangeId,
    layer: gap.expectedChildLayer as MasterMapLayer,
    sourceTimeframe: ({ WEEKLY: 'W1', DAILY: 'D1', INTRADAY: 'H1' } as Record<string, string>)[gap.expectedChildLayer],
    mode: 'all',
    range: node,
    reason: 'GAP',
    eventId: null,
    preferredAnchorTime: gap.coverage?.first_gap_start || node.activeFromTime,
    visibleStart: gap.coverage?.first_gap_start || node.activeFromTime,
    visibleEnd: gap.coverage?.first_gap_end || node.inactiveFromTime,
  };
}
