import courseFiles from 'virtual:course-files';
import { h } from './dom.js';
import { codicon } from './icons.js';

const FILE_ICONS = { md: ['markdown', 'file-blue'], json: ['json', 'file-yellow'], default: ['file', 'file-muted'] };

export function fileIcon(path) {
  const [name, tone] = FILE_ICONS[path.split('.').pop()] ?? FILE_ICONS.default;
  return codicon(name, `file-icon.${tone}`);
}

function tree(paths) {
  const root = { folders: new Map(), files: [] };
  for (const path of paths) {
    const parts = path.split('/');
    let node = root;
    for (const part of parts.slice(0, -1)) {
      if (!node.folders.has(part)) node.folders.set(part, { folders: new Map(), files: [] });
      node = node.folders.get(part);
    }
    node.files.push({ name: parts.at(-1), path });
  }
  return root;
}

const order = (a, b) => a.localeCompare(b, 'en', { sensitivity: 'base' });

export function explorerRows(paths, { fresh = new Set(), active = null } = {}) {
  const rows = [];
  const walk = (node, depth, prefix) => {
    for (const name of [...node.folders.keys()].sort(order)) {
      const path = `${prefix}${name}/`;
      rows.push(h('div.ex-row.ex-folder', { style: { '--depth': depth } }, codicon('chevron-down', 'ex-twist'), h('span.ex-name', { text: name })));
      walk(node.folders.get(name), depth + 1, path);
    }
    for (const file of node.files.sort((a, b) => order(a.name, b.name))) {
      rows.push(h('div.ex-row.ex-file', { style: { '--depth': depth }, class: [fresh.has(file.path) && 'is-fresh', active === file.path && 'is-active'].filter(Boolean).join(' ') },
        h('span.ex-twist'), fileIcon(file.name), h('span.ex-name', { text: file.name })));
    }
  };
  walk(tree(paths), 0, '');
  return rows;
}

const TOKEN = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?)|(true|false|null)|([{}[\],])/g;

function jsonLine(text) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    if (match.index > last) parts.push(document.createTextNode(text.slice(last, match.index)));
    const [whole, string, colon, number, literal] = match;
    if (string) {
      parts.push(h(`span.${colon ? 'tok-key' : 'tok-string'}`, { text: string }));
      if (colon) parts.push(document.createTextNode(colon));
    } else if (number) parts.push(h('span.tok-number', { text: number }));
    else if (literal) parts.push(h('span.tok-literal', { text: literal }));
    else parts.push(h('span.tok-punct', { text: whole }));
    last = match.index + whole.length;
  }
  if (last < text.length) parts.push(document.createTextNode(text.slice(last)));
  return parts;
}

function markdownLine(text) {
  if (/^#{1,6} /.test(text)) return [h('span.tok-heading', { text })];
  if (/^<!--/.test(text)) return [h('span.tok-comment', { text })];
  return text.split(/(`[^`]+`)/).map(part => (part.startsWith('`') ? h('span.tok-string', { text: part }) : document.createTextNode(part)));
}

export function editorLines(path) {
  const source = courseFiles[path]?.text ?? '';
  const highlight = path.endsWith('.json') ? jsonLine : markdownLine;
  return source.split('\n').map((text, index) =>
    h('div.ed-line', {}, h('span.ed-number', { text: String(index + 1) }), h('span.ed-text', {}, highlight(text))));
}

export const lineCount = path => courseFiles[path]?.lines ?? 0;
