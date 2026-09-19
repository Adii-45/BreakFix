/* CodeMirror 6 theme built from the Obsidian Telemetry tokens, so the editor
   is part of the design system rather than a foreign widget dropped into it. */
import { EditorView } from '@codemirror/view';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';

const C = {
  canvas: '#090C17',
  surface1: '#101620',
  surface2: '#171C2A',
  border: '#212838',
  accent: '#FF9900',
  accent2: '#5CD6E0',
  success: '#3DD68C',
  error: '#FF6B6B',
  warning: '#FFB84C',
  text: '#E8EBF0',
  dim: '#8891A3',
  muted: '#525B6C',
};

export const obsidianTheme = EditorView.theme(
  {
    '&': { color: C.text, backgroundColor: C.surface1, fontSize: '13px' },
    '.cm-content': {
      fontFamily: "'JetBrains Mono', ui-monospace, Menlo, monospace",
      padding: '12px 0',
      caretColor: C.accent,
    },
    '.cm-scroller': { fontFamily: "'JetBrains Mono', ui-monospace, Menlo, monospace", lineHeight: '20px' },
    '&.cm-focused': { outline: 'none' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: C.accent, borderLeftWidth: '2px' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
      backgroundColor: 'rgba(255, 153, 0, 0.24)',
    },
    '.cm-activeLine': { backgroundColor: 'rgba(255, 153, 0, 0.06)' },
    '.cm-gutters': {
      backgroundColor: C.canvas,
      color: C.muted,
      border: 'none',
      borderRight: `1px solid ${C.border}`,
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: '11px',
    },
    '.cm-activeLineGutter': { backgroundColor: 'rgba(255, 153, 0, 0.08)', color: C.dim },
    '.cm-lineNumbers .cm-gutterElement': { padding: '0 10px 0 14px' },
    '.cm-matchingBracket, &.cm-focused .cm-matchingBracket': {
      backgroundColor: 'rgba(255, 153, 0, 0.18)',
      outline: `1px solid ${C.border}`,
      color: 'inherit',
    },
    '.cm-selectionMatch': { backgroundColor: 'rgba(92, 214, 224, 0.14)' },
    '.cm-foldPlaceholder': { backgroundColor: C.surface2, border: `1px solid ${C.border}`, color: C.dim },
  },
  { dark: true }
);

export const obsidianHighlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: t.keyword, color: C.accent2 },
    { tag: [t.controlKeyword, t.moduleKeyword], color: C.accent2 },
    { tag: [t.name, t.deleted, t.character, t.macroName], color: C.text },
    { tag: [t.function(t.variableName), t.labelName], color: C.accent },
    { tag: [t.definition(t.name), t.separator], color: C.text },
    { tag: [t.propertyName], color: C.text },
    { tag: [t.typeName, t.className, t.namespace], color: C.warning },
    { tag: [t.number, t.bool, t.null], color: C.success },
    { tag: [t.string, t.special(t.string)], color: C.success },
    { tag: [t.operator, t.operatorKeyword], color: C.accent2 },
    { tag: [t.comment, t.lineComment, t.blockComment], color: C.muted, fontStyle: 'italic' },
    { tag: [t.meta, t.documentMeta], color: C.dim },
    { tag: t.invalid, color: C.error },
    { tag: t.strong, fontWeight: '600' },
    { tag: t.link, color: C.accent, textDecoration: 'underline' },
  ])
);

export const obsidianCodeMirror = [obsidianTheme, obsidianHighlight];
