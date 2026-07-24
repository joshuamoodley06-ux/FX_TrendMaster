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

export function applyUnifiedFilePatch(sourceText: string, filePatch: string): string {
  const newline = sourceText.includes('\r\n') ? '\r\n' : '\n';
  const source = sourceText.replace(/\r\n/g, '\n').split('\n');
  const patchLines = filePatch.replace(/\r\n/g, '\n').split('\n');
  const output: string[] = [];
  let sourceCursor = 0;
  let patchCursor = 0;
  let hunkCount = 0;

  while (patchCursor < patchLines.length) {
    const header = patchLines[patchCursor];
    const match = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(header);
    if (!match) {
      patchCursor += 1;
      continue;
    }

    hunkCount += 1;
    const oldStart = Number(match[1]);
    const expectedOldCount = Number(match[2] || '1');
    const expectedNewCount = Number(match[4] || '1');
    const targetCursor = Math.max(0, oldStart - 1);
    while (sourceCursor < targetCursor) output.push(source[sourceCursor++]);

    patchCursor += 1;
    let consumedOld = 0;
    let producedNew = 0;
    while (patchCursor < patchLines.length && !patchLines[patchCursor].startsWith('@@ ')) {
      const line = patchLines[patchCursor];
      if (line.startsWith('diff --git ')) break;
      if (line === '\\ No newline at end of file') {
        patchCursor += 1;
        continue;
      }
      const prefix = line[0];
      const text = line.slice(1);
      if (prefix === ' ') {
        const actual = source[sourceCursor];
        if (actual !== text) {
          throw new Error(`[structural-anchor-wip] Context mismatch in hunk ${hunkCount} at source line ${sourceCursor + 1}.`);
        }
        output.push(actual);
        sourceCursor += 1;
        consumedOld += 1;
        producedNew += 1;
      } else if (prefix === '-') {
        const actual = source[sourceCursor];
        if (actual !== text) {
          throw new Error(`[structural-anchor-wip] Removal mismatch in hunk ${hunkCount} at source line ${sourceCursor + 1}.`);
        }
        sourceCursor += 1;
        consumedOld += 1;
      } else if (prefix === '+') {
        output.push(text);
        producedNew += 1;
      }
      patchCursor += 1;
    }

    if (consumedOld !== expectedOldCount || producedNew !== expectedNewCount) {
      throw new Error(
        `[structural-anchor-wip] Hunk ${hunkCount} count mismatch: old ${consumedOld}/${expectedOldCount}, new ${producedNew}/${expectedNewCount}.`,
      );
    }
  }

  if (!hunkCount) throw new Error('[structural-anchor-wip] No main.tsx hunks found.');
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
