export function isTypingInEditableField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = String(el.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  if (typeof el.closest === 'function') {
    return !!el.closest('[contenteditable="true"]');
  }
  return false;
}

export type MapStudioKeyAction =
  | 'set-rh'
  | 'set-rl'
  | 'bos-up'
  | 'bos-down'
  | 'replay-back'
  | 'replay-forward'
  | 'undo'
  | 'escape';

export function resolveMapStudioKeyAction(key: string): MapStudioKeyAction | null {
  if (key === 'h' || key === 'H') return 'set-rh';
  if (key === 'l' || key === 'L') return 'set-rl';
  if (key === 'ArrowUp') return 'bos-up';
  if (key === 'ArrowDown') return 'bos-down';
  if (key === 'ArrowLeft') return 'replay-back';
  if (key === 'ArrowRight') return 'replay-forward';
  if (key === 'u' || key === 'U') return 'undo';
  if (key === 'Escape') return 'escape';
  return null;
}
