export function isTypingInEditableField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = String(el.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || tag === 'A') return true;
  if (el.isContentEditable) return true;
  if (typeof el.closest === 'function') {
    return !!el.closest('[contenteditable="true"], [role="textbox"], [role="combobox"], [data-code-editor], .monaco-editor, .cm-editor');
  }
  return false;
}

export type RangeSaveShortcutState = {
  hasValidDraft: boolean;
  saveInFlight: boolean;
  modalOpen: boolean;
};

export function shouldHandleRangeSaveShortcut(
  event: Pick<KeyboardEvent, 'key' | 'repeat' | 'target'>,
  state: RangeSaveShortcutState,
): boolean {
  return event.key === 'Enter'
    && !event.repeat
    && !isTypingInEditableField(event.target)
    && state.hasValidDraft
    && !state.saveInFlight
    && !state.modalOpen;
}

export type RangeSaveShortcutGate = { inFlight: boolean };

export async function runRangeSaveShortcut(
  event: Pick<KeyboardEvent, 'key' | 'repeat' | 'target' | 'preventDefault'>,
  state: Omit<RangeSaveShortcutState, 'saveInFlight'>,
  gate: RangeSaveShortcutGate,
  save: () => Promise<boolean>,
): Promise<boolean> {
  if (!shouldHandleRangeSaveShortcut(event, { ...state, saveInFlight: gate.inFlight })) return false;
  event.preventDefault();
  gate.inFlight = true;
  try {
    return await save();
  } finally {
    gate.inFlight = false;
  }
}

export type MapStudioKeyAction =
  | 'set-rh'
  | 'set-rl'
  | 'bos-up'
  | 'bos-down'
  | 'replay-back'
  | 'replay-forward'
  | 'save-range'
  | 'undo'
  | 'escape';

export function resolveMapStudioKeyAction(key: string): MapStudioKeyAction | null {
  if (key === 'h' || key === 'H') return 'set-rh';
  if (key === 'l' || key === 'L') return 'set-rl';
  if (key === 'ArrowUp') return 'bos-up';
  if (key === 'ArrowDown') return 'bos-down';
  if (key === 'ArrowLeft') return 'replay-back';
  if (key === 'ArrowRight') return 'replay-forward';
  if (key === 'Enter') return 'save-range';
  if (key === 'u' || key === 'U') return 'undo';
  if (key === 'Escape') return 'escape';
  return null;
}
