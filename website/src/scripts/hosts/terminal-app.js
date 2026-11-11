import { h, replace } from '../ui/dom.js';
import { lineCount } from '../ui/files.js';
import { promptLine, terminalLines } from '../ui/terminal.js';

const CLAWD = [' ▐▛███▜▌', '▝▜█████▛▘', '  ▘▘ ▝▝ '];

function header(folder) {
  const rows = [['Claude Code', 'v2.1.304'], ['Opus 5.5 with medium effort', null], [`~/courses/${folder}`, null]];
  return h('div.cc-header', {}, rows.map(([text, version], index) =>
    h('div.t-line', {},
      h('span.cc-clawd', { text: CLAWD[index].padEnd(10) }),
      h(index ? 'span.t-muted' : 'span.t-bold', { text }),
      version ? h('span.t-muted', { text: ` ${version}` }) : null)));
}

const TOOL = {
  mcp: item => [`tum - ${item.name} (MCP)`, `(${item.detail ? `"${item.detail}"` : ''})`, item.result],
  shell: item => ['Bash', `(${item.name})`, item.result],
  edit: item => ['Write', `(${item.name})`, `Wrote ${lineCount(item.name)} lines to ${item.name}`],
  skill: item => ['Skill', `(${item.name})`, item.result],
};

function conversation(items, command) {
  return items.flatMap(item => {
    if (item.role === 'user') return [h('div.t-line.cc-user', {}, h('span.t-muted', { text: '> ' }), h('span', { text: item.text.replace('{command}', command) })), h('div.t-line', {}, h('br'))];
    if (item.role === 'agent') return [h('div.t-line.cc-say', {}, h('span.cc-dot', { text: '⏺ ' }), h('span', { text: item.text })), h('div.t-line', {}, h('br'))];
    const [name, args, result] = TOOL[item.kind](item);
    return [
      h('div.t-line', {}, h('span.cc-dot.is-ok', { text: '⏺ ' }), h('span.t-bold', { text: name }), h('span.t-muted', { text: args })),
      result ? h('div.t-line', {}, h('span.t-muted', { text: '  ⎿  ' }), h('span.t-muted', { text: result })) : null,
    ].filter(Boolean);
  });
}

function promptBox(text, caret) {
  return h('div.cc-prompt', {},
    h('div.cc-rule'),
    h('div.t-line', {}, h('span.cc-chevron', { text: '❯ ' }), text ? h('span', { text }) : h('span.t-muted', { text: 'Try "explain this week\'s lecture"' }), caret ? h('span.t-caret') : null),
    h('div.cc-rule'),
    h('div.t-line.t-muted', { text: '  ? for shortcuts' }));
}

export function createTerminalApp({ marks }) {
  const tabs = h('div.tm-tabs');
  const title = h('span.tm-title');
  const screen = h('div.tm-screen.term');
  const element = h('div.tm', {},
    h('div.tm-titlebar', {}, h('span.traffic', {}, h('i'), h('i'), h('i')), title),
    tabs, screen);
  let last = '';

  function update(view) {
    element.dataset.focus = view.focus;
    const inClaude = view.chatCount > 0 || view.compose.text || (view.folder && !view.terminalStep);
    const studyTab = view.terminalStep && view.folder;
    const key = `${inClaude}|${studyTab}|${view.terminalKey}|${view.terminal?.key}|${view.chatCount}|${view.compose.text}|${view.compose.caret}`;
    if (key === last) return;
    last = key;
    const tabNames = view.folder ? [['claude', !studyTab], ['zsh', studyTab]] : [];
    replace(tabs, tabNames.map(([name, active]) => h('span.tm-tab', { class: active ? 'is-active' : '', text: name })));
    element.dataset.tabs = tabNames.length ? 'yes' : 'no';
    const folder = view.course.folder;
    if (studyTab || !inClaude) {
      title.textContent = `${view.folder ? folder : '~'} — zsh — 100×32`;
      replace(screen, view.terminal ? terminalLines(view.terminal, { prompt: view.folder ? `${folder} %` : '~ %' }) : null);
    } else {
      title.textContent = `${folder} — claude — 100×32`;
      replace(screen, promptLine('claude', 'claude', { prompt: `${folder} %` }), header(folder), h('div.t-line', {}, h('br')),
        conversation(view.chat, view.command), promptBox(view.compose.text, view.compose.caret),
        h('div.t-line.t-muted', { text: '  ⏵⏵ auto mode on (shift+tab to cycle)' }));
    }
    screen.scrollTop = screen.scrollHeight;
  }

  return { element, update, marks };
}
