import { h } from '../ui/dom.js';
import { codicon } from '../ui/icons.js';
import { fileIcon, lineCount } from '../ui/files.js';

const base = path => path.split('/').pop();

const LABELS = {
  codex: {
    mcp: item => ['Called', `tum.${item.name}`],
    shell: item => ['Ran', item.name],
    edit: item => ['Edited', base(item.name)],
    skill: item => ['Read', `${item.name} skill`],
  },
  cursor: {
    mcp: item => ['Called MCP tool', item.name],
    shell: item => ['Ran command', item.name],
    edit: item => ['Edited', base(item.name)],
    skill: item => ['Read', `${item.name}/SKILL.md`],
  },
  antigravity: {
    mcp: item => ['MCP tool', item.name],
    shell: item => ['Ran command', item.name],
    edit: item => ['Edited', base(item.name)],
    skill: item => ['Analyzed', `${item.name}/SKILL.md`],
  },
};

const ICONS = { mcp: 'tools', shell: 'terminal', edit: 'edit', skill: 'book' };

function toolRow(host, item) {
  const [verb, object] = LABELS[host][item.kind](item);
  const added = item.kind === 'edit' ? lineCount(item.name) : 0;
  return h('div.ch-tool', { dataset: { kind: item.kind } },
    codicon(ICONS[item.kind], 'ch-tool-icon'),
    h('span.ch-verb', { text: verb }),
    item.kind === 'edit' ? fileIcon(item.name) : null,
    h(`span.ch-object${item.kind === 'shell' ? '.is-code' : ''}`, { text: object }),
    added ? h('span.ch-added', { text: `+${added}` }) : null,
    item.result && item.kind !== 'edit' ? h('span.ch-result', { text: item.result }) : null);
}

export function chatItems(host, items, command) {
  return items.map(item => {
    const text = item.text?.replace('{command}', command);
    if (item.role === 'user') return h('div.ch-user', {}, h('div.ch-bubble', { text }));
    if (item.role === 'agent') return h('div.ch-agent', { text });
    return toolRow(host, item);
  });
}

const COMPOSERS = {
  codex: { placeholder: 'Ask Codex anything. @ to use plugins or mention files', chips: [['plus', ''], ['vm', 'Local'], ['sparkle', 'GPT-6.1 Terra']], send: 'arrow-up' },
  cursor: { placeholder: 'Plan, search, build anything', chips: [['infinity', 'Agent'], ['', 'Auto']], send: 'arrow-up' },
  antigravity: { placeholder: 'Ask anything, @ for context', chips: [['add', ''], ['chevron-down', 'Planning'], ['chevron-down', 'Gemini 3.1 Pro']], send: 'arrow-right' },
};

export function composer(host, text, caret) {
  const spec = COMPOSERS[host];
  return h('div.ch-composer', {},
    h('div.ch-input', {}, text
      ? [h('span.ch-typed', { text }), caret ? h('span.ch-caret', { 'aria-hidden': 'true' }) : null]
      : h('span.ch-placeholder', { text: spec.placeholder })),
    h('div.ch-controls', {},
      ...spec.chips.map(([icon, label]) => h('span.ch-chip', {}, icon ? codicon(icon) : null, label ? h('span', { text: label }) : null, label && host !== 'antigravity' ? codicon('chevron-down', 'ch-chip-caret') : null)),
      h('span.ch-send', { class: text ? 'is-ready' : '' }, codicon(spec.send))));
}
