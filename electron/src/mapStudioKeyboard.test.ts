import { describe, expect, it, vi } from 'vitest';
import { isTypingInEditableField, resolveMapStudioKeyAction, runRangeSaveShortcut, shouldHandleRangeSaveShortcut } from './mapStudioKeyboard';

describe('mapStudioKeyboard', () => {
  it('maps skeleton mapping keys', () => {
    expect(resolveMapStudioKeyAction('h')).toBe('set-rh');
    expect(resolveMapStudioKeyAction('L')).toBe('set-rl');
    expect(resolveMapStudioKeyAction('ArrowUp')).toBe('bos-up');
    expect(resolveMapStudioKeyAction('ArrowDown')).toBe('bos-down');
    expect(resolveMapStudioKeyAction('ArrowLeft')).toBe('replay-back');
    expect(resolveMapStudioKeyAction('ArrowRight')).toBe('replay-forward');
    expect(resolveMapStudioKeyAction('Enter')).toBe('save-range');
    expect(resolveMapStudioKeyAction('u')).toBe('undo');
    expect(resolveMapStudioKeyAction('Escape')).toBe('escape');
  });

  it('detects editable field tags without DOM', () => {
    expect(isTypingInEditableField({ tagName: 'INPUT' } as EventTarget)).toBe(true);
    expect(isTypingInEditableField({ tagName: 'TEXTAREA' } as EventTarget)).toBe(true);
    expect(isTypingInEditableField({ tagName: 'SELECT' } as EventTarget)).toBe(true);
    expect(isTypingInEditableField({ tagName: 'BUTTON' } as EventTarget)).toBe(true);
    expect(isTypingInEditableField({ tagName: 'DIV' } as EventTarget)).toBe(false);
  });

  it('allows Enter only for one valid, unblocked plotted-range save', () => {
    const event = { key: 'Enter', repeat: false, target: { tagName: 'DIV' } as EventTarget };
    expect(shouldHandleRangeSaveShortcut(event, { hasValidDraft: true, saveInFlight: false, modalOpen: false })).toBe(true);
    expect(shouldHandleRangeSaveShortcut({ ...event, repeat: true }, { hasValidDraft: true, saveInFlight: false, modalOpen: false })).toBe(false);
    expect(shouldHandleRangeSaveShortcut(event, { hasValidDraft: false, saveInFlight: false, modalOpen: false })).toBe(false);
    expect(shouldHandleRangeSaveShortcut(event, { hasValidDraft: true, saveInFlight: true, modalOpen: false })).toBe(false);
    expect(shouldHandleRangeSaveShortcut(event, { hasValidDraft: true, saveInFlight: false, modalOpen: true })).toBe(false);
  });

  it('ignores Enter in form, editor, editable, and modal-owned contexts', () => {
    const state = { hasValidDraft: true, saveInFlight: false, modalOpen: false };
    for (const tagName of ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON']) {
      expect(shouldHandleRangeSaveShortcut({ key: 'Enter', repeat: false, target: { tagName } as EventTarget }, state)).toBe(false);
    }
    const editor = { tagName: 'DIV', isContentEditable: false, closest: (selector: string) => selector.includes('[data-code-editor]') ? {} : null } as unknown as EventTarget;
    expect(shouldHandleRangeSaveShortcut({ key: 'Enter', repeat: false, target: editor }, state)).toBe(false);
    const editable = { tagName: 'DIV', isContentEditable: true } as unknown as EventTarget;
    expect(shouldHandleRangeSaveShortcut({ key: 'Enter', repeat: false, target: editable }, state)).toBe(false);
    expect(shouldHandleRangeSaveShortcut({ key: 'Enter', repeat: false, target: { tagName: 'DIV' } as EventTarget }, { ...state, modalOpen: true })).toBe(false);
  });

  it('runs the existing save callback exactly once while a save is in flight', async () => {
    let resolveSave!: (value: boolean) => void;
    const save = vi.fn(() => new Promise<boolean>((resolve) => { resolveSave = resolve; }));
    const preventDefault = vi.fn();
    const event = { key: 'Enter', repeat: false, target: { tagName: 'DIV' } as EventTarget, preventDefault };
    const gate = { inFlight: false };
    const first = runRangeSaveShortcut(event, { hasValidDraft: true, modalOpen: false }, gate, save);
    const second = await runRangeSaveShortcut(event, { hasValidDraft: true, modalOpen: false }, gate, save);
    expect(second).toBe(false);
    expect(save).toHaveBeenCalledTimes(1);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    resolveSave(true);
    await expect(first).resolves.toBe(true);
  });
});
