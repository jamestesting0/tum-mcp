import { terminalPlan } from '../story/play.js';
import { h, slice } from './dom.js';

const span = ([text, style]) => (style ? h(`span.t-${style}`, { text }) : document.createTextNode(text));
const line = parts => h('div.t-line', {}, parts.length ? parts.map(span) : h('br'));

export function promptLine(command, typed, { prompt = '~ %', caret = false } = {}) {
  return h('div.t-line.t-prompt', {},
    h('span.t-promptmark', { text: `${prompt} ` }),
    h('span.t-command', { text: typed }),
    caret ? h('span.t-caret', { 'aria-hidden': 'true' }) : null);
}

// What the terminal shows `ms` into its step, and a key that changes only when that does.
// A command is typed, its output follows; while a program runs there is no prompt below it.
export function terminalView(blocks, frames, ms) {
  const { events } = terminalPlan(blocks, frames);
  const shown = [];
  let typed = null;
  for (const event of events) {
    if (ms < event.at) break;
    if (event.kind === 'command' && event.duration && ms < event.at + event.duration) {
      typed = slice(event.block.command, (ms - event.at) / event.duration).length;
      shown.push(event);
      break;
    }
    shown.push(event);
  }
  return { shown, typed, key: `${shown.length}|${typed}` };
}

export function terminalLines(view, options) {
  const rows = [];
  let screenStart = -1;
  let running = false;
  for (const event of view.shown) {
    if (event.kind === 'command') {
      const typing = view.typed != null && event === view.shown.at(-1);
      const command = event.block.command;
      rows.push(promptLine(command, typing ? command.slice(0, view.typed) : command, { ...options, caret: typing }));
      if (typing) return rows;
      running = true;
      screenStart = -1;
    } else if (event.kind === 'lines') {
      rows.push(...event.block.lines.map(line));
      if (event.block.exits) running = false;
    } else if (event.kind === 'screen') {
      if (screenStart >= 0) rows.length = screenStart;
      screenStart = rows.length;
      rows.push(...event.screen.map(line));
      if (event.exits) running = false;
    }
  }
  if (!running) rows.push(promptLine('', '', { ...options, caret: true }));
  return rows;
}
