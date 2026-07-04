const fs = require('fs');
const content = fs.readFileSync('electron/src/main.tsx', 'utf-8');

// I will extract:
// - structuralRangePaddingCandles
// - structuralRangeFitPadRatio
// - structuralRangeFitDomain
// - structuralContextTargetTime
// - clampFitTimesToCandles
// - buildCandleWindowFit
// - candleDataExtent
// - isPlausibleMarketTimeMs
// - parseStructuralTimeMs
// - candleIndexAtOrBefore
// - candleIndexAtOrAfter
// - resolveCandleLoadWindow

const extractFunctions = [
  'structuralRangePaddingCandles',
  'structuralRangeFitPadRatio',
  'structuralRangeFitDomain',
  'structuralContextTargetTime',
  'clampFitTimesToCandles',
  'buildCandleWindowFit',
  'candleDataExtent',
  'isPlausibleMarketTimeMs',
  'parseStructuralTimeMs',
  'candleIndexAtOrBefore',
  'candleIndexAtOrAfter',
  'resolveCandleLoadWindow',
  'candleTimeMs',
  'normalizeCandleTime',
  'safeArray',
  'collectParentContextChain',
  'collectHierarchyPathIds',
  'getContextStackPathIds',
  'resolveMappingContextRange',
  'formatStructuralRangeOptionLabel',
  'normalizeStructureLayer',
];

const lines = content.split('\n');

for (const fn of extractFunctions) {
  let found = false;
  for(let i=0; i<lines.length; i++) {
    if (lines[i].startsWith(`function ${fn}(`)) {
      found = true;
      break;
    }
  }
  if (!found) {
    console.log(`Could not find ${fn}`);
  }
}
