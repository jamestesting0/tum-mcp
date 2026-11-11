import { h, replace } from '../ui/dom.js';
import { codicon } from '../ui/icons.js';
import { editorLines, explorerRows, fileIcon } from '../ui/files.js';
import { terminalLines } from '../ui/terminal.js';
import { chatItems, composer } from './chat.js';

const PRODUCT = { codex: 'Visual Studio Code', cursor: 'Cursor', antigravity: 'Antigravity' };
const ACTIVITY = {
  codex: ['files', 'search', 'source-control', 'debug-alt', 'extensions', 'codex'],
  cursor: ['files', 'search', 'source-control', 'extensions'],
  antigravity: ['files', 'search', 'source-control', 'debug-alt', 'extensions'],
};
const AGENT_TITLE = { codex: 'CODEX', cursor: 'New Agent', antigravity: 'Agent' };

function activityIcon(name, marks) {
  if (name === 'codex') return h('span.wb-act.is-mark', { title: 'Codex' }, marks.codex());
  return h('span.wb-act', { class: name === 'files' ? 'is-active' : '' }, codicon(name));
}

export function createWorkbench(host, { marks }) {
  const title = h('span.wb-title-text');
  const explorerHead = h('div.wb-side-title');
  const explorer = h('div.wb-tree');
  const tabs = h('div.wb-tabs');
  const crumbs = h('div.wb-crumbs');
  const editor = h('div.wb-editor-body');
  const terminal = h('div.wb-terminal.term');
  const thread = h('div.ch-thread');
  const compose = h('div.ch-compose-slot');
  const terminalHeader = h('div.wb-panel-tabs', {},
    ['Problems', 'Output', 'Debug Console', 'Terminal', 'Ports'].map(name => h('span.wb-panel-tab', { class: name === 'Terminal' ? 'is-active' : '', text: name.toUpperCase() })),
    h('span.wb-panel-spacer'), h('span.wb-panel-shell', {}, codicon('terminal'), h('span', { text: 'zsh' })));
  const activities = ACTIVITY[host].map(name => activityIcon(name, marks));

  const element = h(`div.wb.wb-${host}`, {},
    h('div.wb-titlebar', {},
      h('span.traffic', {}, h('i'), h('i'), h('i')),
      host === 'cursor' ? h('span.wb-title-search', {}, codicon('search'), title) : title,
      h('span.wb-title-actions', {}, codicon('layout-sidebar-left'), codicon('layout-panel'), codicon('layout-sidebar-right'))),
    h('div.wb-body', {},
      host === 'cursor' ? null : h('div.wb-activity', {}, activities, h('span.wb-act-spacer'), h('span.wb-act', {}, codicon('account')), h('span.wb-act', {}, codicon('settings-gear'))),
      h('div.wb-side', {},
        host === 'cursor' ? h('div.wb-activity-row', {}, activities) : null,
        explorerHead, explorer),
      h('div.wb-main', {},
        h('div.wb-editor', {}, tabs, crumbs, editor),
        h('div.wb-panel', {}, terminalHeader, terminal)),
      h('div.wb-aux', {},
        h('div.wb-aux-head', {}, host === 'cursor' ? h('span.wb-aux-tab', {}, h('span', { text: AGENT_TITLE[host] }), codicon('close')) : h('span.wb-aux-title', { text: AGENT_TITLE[host] }),
          h('span.wb-aux-actions', {}, codicon('add'), codicon('history'), codicon('ellipsis'))),
        thread, compose)),
    h('div.wb-status', {}, h('span', {}, codicon('remote')), h('span', {}, codicon('source-control'), h('span', { text: 'main' })), h('span.wb-status-spacer'), h('span', { text: 'Ln 1, Col 1' }), h('span', { text: 'UTF-8' })));

  let last = {};
  function update(view) {
    element.dataset.focus = view.focus;
    element.dataset.folder = view.folder ? 'open' : 'none';
    element.dataset.terminal = view.terminal?.shown.length ? 'used' : 'empty';
    title.textContent = view.folder ? view.course.folder : PRODUCT[host];

    const filesKey = `${view.folder}|${view.files.join(',')}|${[...view.fresh].join(',')}|${view.editor}`;
    if (filesKey !== last.files) {
      last.files = filesKey;
      replace(explorerHead, h('span', { text: 'EXPLORER' }), h('span.wb-side-actions', {}, codicon('ellipsis')));
      if (!view.folder) {
        replace(explorer, h('div.wb-tree-section', {}, codicon('chevron-down'), h('span', { text: 'NO FOLDER OPENED' })),
          h('p.wb-empty', { text: 'You have not yet opened a folder.' }), h('span.wb-button', { text: 'Open Folder' }));
      } else {
        replace(explorer, h('div.wb-tree-section', {}, codicon('chevron-down'), h('span', { text: view.course.folder.toUpperCase() })),
          explorerRows(view.files, { fresh: view.fresh, active: view.editor }));
      }
      if (view.editor && view.files.includes(view.editor)) {
        replace(tabs, h('span.wb-tab.is-active', {}, fileIcon(view.editor), h('span', { text: view.editor.split('/').pop() }), codicon('close')));
        replace(crumbs, ...view.editor.split('/').flatMap((part, index, all) => [h('span', { text: part }), index < all.length - 1 ? codicon('chevron-right') : null]));
        replace(editor, h('div.wb-code', {}, editorLines(view.editor)));
        element.dataset.editor = 'file';
      } else {
        replace(tabs); replace(crumbs);
        replace(editor, h('div.wb-watermark', {}, marks.product(host),
          h('dl', {}, ...[['Show All Commands', '⇧⌘P'], ['Go to File', '⌘P'], ['Find in Files', '⇧⌘F'], ['Toggle Terminal', '⌃`']].flatMap(([label, keys]) => [h('dt', { text: label }), h('dd', { text: keys })]))));
        element.dataset.editor = 'empty';
      }
    }

    const terminalKey = `${view.terminalKey}|${view.terminal?.key}|${view.folder}`;
    if (terminalKey !== last.terminal) {
      last.terminal = terminalKey;
      replace(terminal, view.terminal ? terminalLines(view.terminal, { prompt: view.folder ? `${view.course.folder} %` : '~ %' }) : null);
    }

    const chatKey = `${view.chatCount}|${view.compose.text}|${view.compose.caret}`;
    if (chatKey !== last.chat) {
      last.chat = chatKey;
      replace(thread, chatItems(host, view.chat, view.command));
      replace(compose, composer(host, view.compose.text, view.compose.caret));
    }
    // Panels change size with focus and layout, so keep the newest line in view on every update.
    terminal.scrollTop = terminal.scrollHeight;
    thread.scrollTop = thread.scrollHeight;
  }

  return { element, update };
}
