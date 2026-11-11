// Terminal frames for each host. Setup screens are recorded from the real CLI
// (npm run capture-cli); the screens no safe capture can reach are derived here.
import codex from '../../content/cli/setup-codex.json';
import claude from '../../content/cli/setup-claude.json';
import cursor from '../../content/cli/setup-cursor.json';
import antigravity from '../../content/cli/setup-antigravity.json';
import login from '../../content/cli/login.json';

const recorded = { codex, claude, cursor, antigravity };
const WORKFLOWS = ['Lecture', 'Audio Notes', 'Video Notes', 'Course Memory'];
const text = line => line.map(([value]) => value).join('');

// The capture cancels the workflow step so nothing installs. After Enter, setup prints the
// answer ("done (4 selections)", questionary's wording) and one status row per workflow
// (lifecycle._install_workflows: "On", "Installed."), then the same Next steps.
function installed(screen) {
  const question = screen.findIndex(line => text(line).includes('Add optional workflows?'));
  const lines = screen.map(line => line.map(span => [...span]));
  lines[question] = [...lines[question], [' done (4 selections)', 'accent']];
  const width = Math.max(...WORKFLOWS.map(name => name.length));
  const rows = WORKFLOWS.map(name => [[name.padEnd(width), ''], ['  ', ''], ['✓ ', 'ready'], ['On', ''], ['  Installed.', '']]);
  return [...lines.slice(0, question + 1), [], ...rows, ...lines.slice(question + 1)];
}

// The capture's throwaway HOME has no Claude Code sign-in, so its client check says
// "Needs action". A signed-in Claude Code gets the READY row from clients/verification.py,
// wrapped like the CLI wraps it at the capture's 88 columns.
const COLUMNS = 88;
const CLAUDE_READY = "Loaded by the app with its TUM tools and course hooks; the app's workspace trust settings still apply.";

function wrap(value, width) {
  const lines = [''];
  for (const word of value.split(' ')) {
    const last = lines.at(-1);
    if (last && last.length + 1 + word.length > width) lines.push(word);
    else lines[lines.length - 1] = last ? `${last} ${word}` : word;
  }
  return lines;
}

function claudeReady(screen) {
  const row = screen.findIndex(line => text(line).startsWith('Claude Code  '));
  let end = row + 1;
  while (end < screen.length && /^\s+\S/.test(text(screen[end]))) end += 1;
  const indent = 'Claude Code  ✓ Ready  '.length;
  const [first, ...rest] = wrap(CLAUDE_READY, COLUMNS - indent);
  const rows = [[['Claude Code  ', ''], ['✓ ', 'ready'], [`Ready  ${first}`, '']], ...rest.map(line => [[' '.repeat(indent) + line, '']])];
  return [...screen.slice(0, row), ...rows, ...screen.slice(end)];
}

// Pickers redraw in place, so the steps between two recorded screens are the same rows with
// the pointer and ticks moved: Space ticks the row under the pointer, ↓ moves the pointer.
const HOST_ROW = { codex: 0, claude: 1, cursor: 2, antigravity: 3 };
// Frames that are a series of screens, shown one after another, rather than one screen.
export const SEQUENCES = new Set(['pick-agent', 'pick-workflows', 'login-pick']);
const isRow = line => /^ (>| ) [○●] /.test(text(line));
const isOption = line => /^ (>| ) \S/.test(text(line)) && !isRow(line);

// Text after the first n characters of a line, keeping each run's style.
function drop(line, n) {
  const out = [];
  let left = n;
  for (const [value, style] of line) {
    if (left >= value.length) { left -= value.length; continue; }
    out.push([value.slice(left), style]);
    left = 0;
  }
  return out;
}

// A row's label, with its status (`Not set up`, `not set up`) muted as the CLI prints it.
function label(line) {
  const rest = drop(line, 5);
  if (rest.some(([, style]) => style === 'muted')) return rest;
  const whole = text(rest);
  const status = whole.match(/^(.*?)(\s{2,}(?:Not set up|not set up))$/);
  return status ? [[status[1], ''], [status[2], 'muted']] : rest;
}

function picker(screen, pointer, ticked) {
  const rows = screen.map((line, index) => (isRow(line) ? index : -1)).filter(index => index >= 0);
  return screen.map((line, index) => {
    const row = rows.indexOf(index);
    if (row < 0) return line;
    const at = row === pointer;
    return [[at ? ' > ' : '   ', at ? 'accent' : ''], ticked.has(row) ? ['● ', 'bold'] : ['○ ', ''], ...label(line)];
  });
}

function options(screen, pointer) {
  let row = -1;
  return screen.map(line => {
    if (!isOption(line)) return line;
    row += 1;
    return [[row === pointer ? ' > ' : '   ', row === pointer ? 'accent' : ''], [text(line).slice(3), '']];
  });
}

// The CLI prints its hints muted; the recording keeps only colours, so they are restored here.
const HINTS = /^(↑\/↓ |Waiting up to |Completed connections )/;
const muteHints = screen => screen.map(line => (HINTS.test(text(line)) ? [[text(line), 'muted']] : line));

function setupFrames(screens, host) {
  const row = HOST_ROW[host];
  const pickAgent = [];
  for (let at = 1; at <= row; at += 1) pickAgent.push(picker(screens.clients, at, new Set()));
  pickAgent.push(picker(screens.clients, row, new Set([row])));
  const pickWorkflows = [picker(screens.workflows, 0, new Set())];
  const ticked = new Set();
  for (let at = 0; at < WORKFLOWS.length; at += 1) {
    if (at) pickWorkflows.push(picker(screens.workflows, at, new Set(ticked)));
    ticked.add(at);
    pickWorkflows.push(picker(screens.workflows, at, new Set(ticked)));
  }
  return {
    clients: picker(screens.clients, 0, new Set()),
    'pick-agent': pickAgent,
    'pick-workflows': pickWorkflows,
    'clients-picked': pickAgent.at(-1),
    'workflows-picked': pickWorkflows.at(-1),
    installed: installed(screens.next),
  };
}

// After the browser list: questionary prints the answer, then login says where it opens.
function loginFrames() {
  const { services, browser } = login.screens;
  const question = browser.findIndex(line => text(line).startsWith(' Choose browser'));
  const opening = [
    ...browser.slice(0, question),
    [[' Choose browser Google Chrome', 'bold']],
    [],
    [['Opening Moodle in Google Chrome.', '']],
    [['Sign in there and complete MFA.', '']],
    [['Waiting up to 10 minutes. Press Ctrl+C to stop waiting.', 'muted']],
    [['Completed connections are saved.', 'muted']],
    [],
  ];
  return {
    'login-pick': [picker(services, 0, new Set()), picker(services, 0, new Set([0])), options(browser, 0)],
    'login-opening': opening,
    'login-done': [...opening, [['✓ ', 'ready'], ['Moodle connected', '']], [], [['Next: ask your coding agent about your courses, for example “What is due this week?”', '']]],
  };
}

export function cliFrames(host) {
  let screens = recorded[host];
  if (host === 'claude') {
    screens = { ...screens, ...Object.fromEntries(['workflows', 'workflows-selected', 'next'].map(key => [key, claudeReady(screens[key])])) };
  }
  const frames = { ...setupFrames(screens, host), ...loginFrames() };
  return Object.fromEntries(Object.entries(frames).map(([name, value]) => [name, SEQUENCES.has(name) ? value.map(muteHints) : muteHints(value)]));
}
