import { describe, expect, it } from 'vitest';
import { isTypingInEditableField, resolveMapStudioKeyAction } from './mapStudioKeyboard';

describe('mapStudioKeyboard', () => {
  it('maps skeleton mapping keys', () => {
    expect(resolveMapStudioKeyAction('h')).toBe('set-rh');
    expect(resolveMapStudioKeyAction('L')).toBe('set-rl');
    expect(resolveMapStudioKeyAction('ArrowUp')).toBe('bos-up');
    expect(resolveMapStudioKeyAction('ArrowDown')).toBe('bos-down');
    expect(resolveMapStudioKeyAction('ArrowLeft')).toBe('replay-back');
    expect(resolveMapStudioKeyAction('ArrowRight')).toBe('replay-forward');
    expect(resolveMapStudioKeyAction('u')).toBe('undo');
    expect(resolveMapStudioKeyAction('Escape')).toBe('escape');
  });

  it('detects editable field tags without DOM', () => {
    expect(isTypingInEditableField({ tagName: 'INPUT' } as EventTarget)).toBe(true);
    expect(isTypingInEditableField({ tagName: 'DIV' } as EventTarget)).toBe(false);
  });
});
