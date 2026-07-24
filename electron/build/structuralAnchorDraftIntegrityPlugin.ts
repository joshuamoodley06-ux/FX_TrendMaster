import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import type { Plugin } from 'vite';

const TARGET_PATH = 'electron/src/main.tsx';
const PATCH_PAYLOAD_URL = new URL('./structuralAnchorDraftIntegrity.patch.zlib.b64', import.meta.url);

function readPatchText(): string {
  const encoded = readFileSync(PATCH_PAYLOAD_URL, 'utf8').trim();
  return inflateSync(Buffer.from(encoded, 'base64')).toString('utf8');
}

function extractFilePatch(patchText: string, targetPath: string): string {
  const normalized = patchText.replace(/\r\n/g, '\n');
  const marker = `diff --git a/${targetPath} b/${targetPath}`;
  const start = normalized.indexOf(marker);
  if (start < 0) throw new Error(`[structural-anchor-wip] Missing patch section for ${targetPath}`);
  const next = normalized.indexOf('\ndiff --git ', start + marker.length);
  return normalized.slice(start, next < 0 ? normalized.length : next);
}

type ParsedHunk = {
  expectedOldStart: number;
  expectedOldCount: number;
  expectedNewCount: number;
  oldLines: string[];
  newLines: string[];
};

function parseHunks(filePatch: string): ParsedHunk[] {
  const patchLines = filePatch.replace(/\r\n/g, '\n').split('\n');
  const hunks: ParsedHunk[] = [];
  let cursor = 0;

  while (cursor < patchLines.length) {
    const match = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(patchLines[cursor]);
    if (!match) {
      cursor += 1;
      continue;
    }

    const hunk: ParsedHunk = {
      expectedOldStart: Number(match[1]),
      expectedOldCount: Number(match[2] || '1'),
      expectedNewCount: Number(match[4] || '1'),
      oldLines: [],
      newLines: [],
    };
    cursor += 1;

    while (cursor < patchLines.length && !patchLines[cursor].startsWith('@@ ')) {
      const line = patchLines[cursor];
      if (line.startsWith('diff --git ')) break;
      if (line === '\\ No newline at end of file') {
        cursor += 1;
        continue;
      }

      const prefix = line[0];
      const text = line.slice(1);
      if (prefix === ' ' || prefix === '-') hunk.oldLines.push(text);
      if (prefix === ' ' || prefix === '+') hunk.newLines.push(text);
      cursor += 1;
    }

    if (hunk.oldLines.length !== hunk.expectedOldCount || hunk.newLines.length !== hunk.expectedNewCount) {
      throw new Error(
        `[structural-anchor-wip] Hunk count mismatch: old ${hunk.oldLines.length}/${hunk.expectedOldCount}, new ${hunk.newLines.length}/${hunk.expectedNewCount}.`,
      );
    }
    hunks.push(hunk);
  }

  if (!hunks.length) throw new Error('[structural-anchor-wip] No main.tsx hunks found.');
  return hunks;
}

function sequenceMatches(source: string[], start: number, expected: string[]): boolean {
  if (start < 0 || start + expected.length > source.length) return false;
  for (let index = 0; index < expected.length; index += 1) {
    if (source[start + index] !== expected[index]) return false;
  }
  return true;
}

function findHunkStart(source: string[], hunk: ParsedHunk, minimumStart: number): number {
  const expectedIndex = Math.max(minimumStart, hunk.expectedOldStart - 1);
  const candidates: number[] = [];

  for (let index = minimumStart; index <= source.length - hunk.oldLines.length; index += 1) {
    if (sequenceMatches(source, index, hunk.oldLines)) candidates.push(index);
  }

  if (!candidates.length) {
    const preview = hunk.oldLines.slice(0, 3).join(' | ');
    throw new Error(`[structural-anchor-wip] Could not locate guarded hunk near source line ${hunk.expectedOldStart}: ${preview}`);
  }

  candidates.sort((left, right) => Math.abs(left - expectedIndex) - Math.abs(right - expectedIndex));
  return candidates[0];
}

export function applyUnifiedFilePatch(sourceText: string, filePatch: string): string {
  const newline = sourceText.includes('\r\n') ? '\r\n' : '\n';
  const source = sourceText.replace(/\r\n/g, '\n').split('\n');
  const output: string[] = [];
  let sourceCursor = 0;

  for (const hunk of parseHunks(filePatch)) {
    const hunkStart = findHunkStart(source, hunk, sourceCursor);
    while (sourceCursor < hunkStart) output.push(source[sourceCursor++]);
    output.push(...hunk.newLines);
    sourceCursor = hunkStart + hunk.oldLines.length;
  }

  while (sourceCursor < source.length) output.push(source[sourceCursor++]);
  return output.join('\n').replace(/\n/g, newline);
}

export function applyStructuralAnchorDraftIntegrity(sourceText: string): string {
  if (sourceText.includes("from './structuralRangeDraftSession'")) return sourceText;
  const transformed = applyUnifiedFilePatch(sourceText, extractFilePatch(readPatchText(), TARGET_PATH));
  const requiredProof = [
    "from './structuralRangeDraftSession'",
    'structuralRangeDraftSessionRef',
    'captureStructuralRangeDraftSnapshot',
    'an older RL cannot be reused',
  ];
  for (const proof of requiredProof) {
    if (!transformed.includes(proof)) {
      throw new Error(`[structural-anchor-wip] Transform proof missing: ${proof}`);
    }
  }
  return transformed;
}

export function structuralAnchorDraftIntegrityPlugin(): Plugin {
  return {
    name: 'fxtm-structural-anchor-draft-integrity-wip',
    enforce: 'pre',
    transform(code, id) {
      const cleanId = id.split('?')[0].replace(/\\/g, '/');
      if (!cleanId.endsWith('/src/main.tsx')) return null;
      return { code: applyStructuralAnchorDraftIntegrity(code), map: null };
    },
  };
}
