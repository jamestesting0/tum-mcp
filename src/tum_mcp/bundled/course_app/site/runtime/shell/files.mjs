import data from '../../data.mjs';
import { node, svgNode, button, append, studyText } from './dom.mjs';
import { renderCode, codeEditor, languageName, lineSet } from '../reading/code.mjs';
import { iconButton } from './navigation.mjs';

// A light code project for a programming exercise: a file tree, tabs for open files,
// read-only files with line numbers and editable files whose drafts stay in this browser.
const span = value => {
  if (!value) return null;
  const [first, last = first] = String(value).split('-').map(Number);
  return { first, last };
};
const icon = d => { const svg = svgNode('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', focusable: 'false' }); svg.append(svgNode('path', { d })); return svg; };
const ICON = {
  file: 'M4 1.5h5l3.5 3.5v9.5h-8.5zM9 1.5V5h3.5',
  folder: 'M1.5 3.5h4.5l1.5 1.5h7v8.5h-13z',
  close: 'M4.5 4.5l7 7M11.5 4.5l-7 7',
  tree: 'M2 3h12v10H2zM6 3v10',
  edit: 'M10.5 2.5l3 3-7.5 7.5H3v-3z',
};
export const fileIcon = kind => icon(ICON[kind]);
const storage = key => `course-app:${data.course.identity}:files:v1:${key}`;
function readDrafts(key) {
  try { const value = JSON.parse(localStorage.getItem(storage(key)) || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  catch { return {}; }
}

// Ask the project on this page that holds `path` to open it, optionally at `lines` and in its
// solved version. A project in the editor workspace moves its own panel, never the page.
export function openInWorkspace(path, lines, { solution = false } = {}) {
  const target = [...document.querySelectorAll('.project')].find(item => item.workspace?.has(path));
  if (!target) return false;
  target.workspace.open(path, lines, { solution });
  const workspace = target.closest('.ide');
  if (workspace?.ide) workspace.ide.reveal('code');
  else target.scrollIntoView({ block: 'start', behavior: 'smooth' });
  return true;
}
const spanSet = spans => new Set((spans || []).flatMap(([first, last]) => Array.from({ length: last - first + 1 }, (_, index) => first + index)));
const TREE = { min: 160, max: 320, start: 220 };

// `ide` places the project in the editor workspace: the workspace owns the tree's visibility,
// the tree resizes by its divider, and opening a file from the tree reports it.
export function renderFiles(block, ide = null) {
  const files = new Map(block.files.map(file => [file.path, file]));
  const drafts = readDrafts(block.key);
  const content = path => typeof drafts[path] === 'string' ? drafts[path] : files.get(path).code;
  const save = () => { try { localStorage.setItem(storage(block.key), JSON.stringify(drafts)); } catch { /* storage blocked: drafts last for this visit */ } };
  const root = node('div', 'project'); root.dataset.workspace = block.key;
  root.setAttribute('role', 'region'); root.setAttribute('aria-label', `Code workspace: ${block.description}`);
  const start = block.open || block.files.find(file => file.editable)?.path || block.files[0].path;
  let open = [start], active = start, marked = new Set();
  const solved = new Set();

  // Folders first, then files, alphabetically; a single top folder chain stays open.
  const tree = { folders: new Map(), files: [] };
  for (const file of block.files) {
    const parts = file.path.split('/'); let level = tree;
    for (const part of parts.slice(0, -1)) { if (!level.folders.has(part)) level.folders.set(part, { folders: new Map(), files: [] }); level = level.folders.get(part); }
    level.files.push(file);
  }
  const fileButtons = new Map();
  function branch(level, depth) {
    const list = node('ul', 'project-tree-list');
    for (let [name, child] of [...level.folders].sort(([a], [b]) => a.localeCompare(b))) {
      // A chain of single folders reads as one row, as in src/de/tum/in/ase.
      while (child.folders.size === 1 && !child.files.length) { const [[next, inner]] = child.folders; name = `${name}/${next}`; child = inner; }
      const folder = node('details', 'project-folder'); folder.open = true;
      const summary = append(node('summary'), icon(ICON.folder), node('span', 'project-file-name', name)); summary.style.setProperty('--depth', depth); summary.title = name;
      folder.append(summary, branch(child, depth + 1));
      list.append(append(node('li'), folder));
    }
    for (const file of [...level.files].sort((a, b) => a.path.localeCompare(b.path))) {
      const name = file.path.split('/').pop();
      const control = button('', () => { show(file.path); if (ide) ide.onOpen?.(file.path); else if (narrow.matches) setTree(false); }, 'project-file');
      control.style.setProperty('--depth', depth);
      control.append(icon(ICON.file), node('span', 'project-file-name', name));
      if (file.editable) { const mark = icon(ICON.edit); mark.classList.add('project-editable'); control.append(mark); }
      control.title = file.editable ? `${file.path} (editable)` : file.path;
      fileButtons.set(file.path, control);
      list.append(append(node('li'), control));
    }
    return list;
  }
  const narrow = matchMedia('(max-width: 719px)');
  const treePanel = append(node('nav', 'project-tree'), branch(tree, 0)); treePanel.setAttribute('aria-label', 'Files');
  const treeToggle = button('', () => setTree(treePanel.hidden), 'quiet project-tree-toggle');
  treeToggle.append(icon(ICON.tree));
  const tabs = node('div', 'project-tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Open files');
  const pathBar = node('div', 'project-path');
  const pane = node('div', 'project-pane'); pane.setAttribute('role', 'tabpanel');
  const editor = append(node('div', 'project-editor'), append(node('div', 'project-bar'), treeToggle, tabs), pathBar, pane);
  const body = append(node('div', 'project-body'), treePanel, editor);
  root.append(body);
  if (ide) {
    root.classList.add('in-workspace');
    const divider = node('div', 'project-tree-divider');
    divider.setAttribute('role', 'separator'); divider.setAttribute('aria-orientation', 'vertical');
    divider.setAttribute('aria-label', 'Resize files'); divider.tabIndex = 0;
    divider.setAttribute('aria-valuemin', String(TREE.min)); divider.setAttribute('aria-valuemax', String(TREE.max));
    const width = value => {
      const clamped = Math.round(Math.min(TREE.max, Math.max(TREE.min, value)));
      body.style.setProperty('--tree-width', `${clamped}px`); divider.setAttribute('aria-valuenow', String(clamped));
      return clamped;
    };
    width(ide.treeWidth || TREE.start);
    divider.addEventListener('pointerdown', event => {
      divider.setPointerCapture(event.pointerId);
      const left = body.getBoundingClientRect().left;
      const move = moved => width(moved.clientX - left);
      const end = () => { divider.removeEventListener('pointermove', move); ide.onTreeWidth?.(width(treePanel.getBoundingClientRect().width)); };
      divider.addEventListener('pointermove', move);
      divider.addEventListener('pointerup', end, { once: true });
    });
    divider.addEventListener('keydown', event => {
      const step = { ArrowLeft: -16, ArrowRight: 16 }[event.key];
      if (!step) return;
      event.preventDefault(); ide.onTreeWidth?.(width(treePanel.getBoundingClientRect().width + step));
    });
    divider.addEventListener('dblclick', () => ide.onTreeWidth?.(width(TREE.start)));
    body.insertBefore(divider, editor);
  }
  // The file tree folds away on any width; phones start with it folded.
  function setTree(open) {
    treePanel.hidden = !open; body.classList.toggle('tree-hidden', !open);
    treeToggle.setAttribute('aria-expanded', String(open));
    treeToggle.setAttribute('aria-label', open ? 'Hide files' : 'Show files'); treeToggle.title = open ? 'Hide files' : 'Show files';
  }
  const syncNarrow = () => setTree(!narrow.matches);
  if (!ide) narrow.addEventListener('change', () => { if (root.isConnected) syncNarrow(); });

  function paintTabs() {
    tabs.replaceChildren();
    for (const path of open) {
      const name = path.split('/').pop(), selected = path === active;
      const tab = button(name, () => show(path), `project-tab${selected ? ' active' : ''}`);
      tab.setAttribute('role', 'tab'); tab.setAttribute('aria-selected', String(selected)); tab.title = path;
      if (typeof drafts[path] === 'string' && drafts[path] !== files.get(path).code) tab.classList.add('changed');
      const item = append(node('span', `project-tab-item${selected ? ' active' : ''}`), tab);
      if (open.length > 1) {
        const close = button('', () => { open = open.filter(other => other !== path); if (active === path) active = open.at(-1); paint(); }, 'quiet project-tab-close');
        close.append(icon(ICON.close)); close.setAttribute('aria-label', `Close ${name}`);
        item.append(close);
      }
      tabs.append(item);
    }
    for (const [path, control] of fileButtons) control.setAttribute('aria-current', String(path === active));
  }
  function paintPath(file) {
    pathBar.replaceChildren();
    // The folder path shortens from the left, so the file name always stays visible.
    const folders = file.path.split('/').slice(0, -1).join('/');
    const crumbs = append(node('span', 'project-crumbs'), append(node('span', 'project-crumbs-inner'), folders ? node('span', 'project-folders', `${folders}/`) : '', node('span', 'project-current', file.path.split('/').pop())));
    crumbs.title = file.path;
    const side = node('span', 'project-meta', [languageName(file.language, file.path), file.editable ? 'editable' : 'read only'].filter(Boolean).join(' · '));
    pathBar.append(crumbs, side);
    if (typeof file.solution === 'string') {
      // Yours is the student's file; Solution is the solved file with the task's changes marked.
      const views = node('span', 'project-views'); views.setAttribute('role', 'group'); views.setAttribute('aria-label', 'Version');
      for (const [label, on] of [['Yours', false], ['Solution', true]]) {
        // Marked lines belong to one version, so switching clears them.
        const choice = button(label, () => { if (on) solved.add(file.path); else solved.delete(file.path); marked = new Set(); paint(); }, 'quiet project-view');
        choice.setAttribute('aria-pressed', String(solved.has(file.path) === on));
        views.append(choice);
      }
      pathBar.append(views);
    }
    if (file.editable && !solved.has(file.path) && typeof drafts[file.path] === 'string' && drafts[file.path] !== file.code) {
      const reset = iconButton('Reset file', 'reset', () => { delete drafts[file.path]; save(); paint(); });
      reset.classList.add('project-reset'); pathBar.append(reset);
    }
  }
  function paintPane(file) {
    pane.replaceChildren();
    if (solved.has(file.path)) {
      pane.append(renderCode(file.solution, file.language || file.path.split('.').pop(), { numbers: true, marked, changed: spanSet(file.changed) }));
      return;
    }
    if (file.editable) {
      const input = node('textarea'); input.value = content(file.path); input.maxLength = 50000;
      input.setAttribute('aria-label', `Edit ${file.path}`);
      input.addEventListener('input', () => {
        drafts[file.path] = input.value; save();
        const wasChanged = pathBar.querySelector('.project-reset') !== null, changed = input.value !== file.code;
        if (wasChanged !== changed) { paintTabs(); paintPath(file); }
      });
      pane.append(codeEditor(input, file.language || file.path.split('.').pop(), marked));
      return;
    }
    pane.append(renderCode(file.code, file.language || file.path.split('.').pop(), { numbers: true, marked }));
  }
  function paint() {
    const file = files.get(active);
    paintTabs(); paintPath(file); paintPane(file);
  }
  function show(path, lines, { solution = false } = {}) {
    if (!open.includes(path)) open = [...open, path].slice(-6);
    if (solution && typeof files.get(path).solution === 'string') solved.add(path);
    active = path; marked = lineSet(lines); paint();
    const first = pane.querySelector('.code-line.marked');
    pane.scrollTop = first ? Math.max(0, first.getBoundingClientRect().top - pane.getBoundingClientRect().top - pane.clientHeight / 3) : 0;
  }
  root.workspace = {
    has: path => files.has(path), open: (path, lines, options) => show(path, lines, options),
    setTree, get treeOpen() { return !treePanel.hidden; },
  };
  if (ide) setTree(ide.treeOpen !== false); else syncNarrow();
  paint();
  return root;
}

// What a step points at: the file, the lines, and a jump into the project above.
// In the editor workspace the code is already beside the step, so a reference is a link.
export function codeReferences(refs, files, { compact = false } = {}) {
  const box = node('div', `code-refs${compact ? ' compact' : ''}`);
  for (const ref of refs) {
    const file = files.get(ref.path);
    if (!file) continue;
    const found = span(ref.lines), all = file.code.split('\n');
    const first = found ? found.first : 1, last = found ? found.last : Math.min(all.length, 30);
    const excerpt = all.slice(first - 1, last).join('\n');
    const card = node('figure', 'code-ref');
    const caption = append(node('figcaption', 'code-ref-head'), icon(ICON.file), append(node('span', 'code-ref-path'), node('bdi', '', ref.path)), node('span', 'code-ref-lines', found ? (first === last ? `line ${first}` : `lines ${first}–${last}`) : ''));
    const jump = button('Open in files', () => openInWorkspace(ref.path, ref.lines), 'quiet code-ref-open');
    caption.append(jump);
    card.append(caption);
    if (!compact) card.append(renderCode(excerpt, file.language || ref.path.split('.').pop(), { numbers: true, start: first }));
    box.append(card);
  }
  return box;
}

// Every project file shown in a list of blocks, by path.
export function filesIn(blocks = []) {
  const map = new Map();
  for (const block of blocks) if (block.kind === 'files') for (const file of block.files) map.set(file.path, file);
  return map;
}

// The solved lines a step writes or a Solution answer shows, read from the solved files, each
// with the walkthrough notes that explain them and a way to open the whole solved file.
// Notes on solved lines: choosing one highlights its lines in the listing above, as a
// walkthrough stop does; choosing it again clears them. Up and Down move between notes.
function codeNotes(stops, listing, first) {
  const lines = [...listing.querySelectorAll('.code-line')];
  const list = node('ul', 'code-notes');
  const choices = stops.map(stop => {
    const at = span(stop.lines);
    const choice = button('', () => select(choice.getAttribute('aria-pressed') === 'true' ? null : choice), 'code-note');
    choice.setAttribute('aria-pressed', 'false'); choice.span = at;
    choice.append(node('span', 'code-note-lines', at.first === at.last ? `Line ${at.first}` : `Lines ${at.first}–${at.last}`), studyText('span', '', stop.note));
    list.append(append(node('li'), choice));
    return choice;
  });
  function select(active) {
    for (const choice of choices) choice.setAttribute('aria-pressed', String(choice === active));
    lines.forEach((line, index) => {
      const number = first + index;
      line.classList.toggle('marked', Boolean(active?.span) && number >= active.span.first && number <= active.span.last);
    });
  }
  list.addEventListener('keydown', event => {
    const step = { ArrowDown: 1, ArrowUp: -1 }[event.key], at = choices.indexOf(document.activeElement);
    if (!step || at < 0) return;
    event.preventDefault(); event.stopPropagation();
    const next = choices[Math.min(choices.length - 1, Math.max(0, at + step))];
    next.focus(); select(next);
  });
  return list;
}
export function solvedCode(refs, files) {
  const box = node('div', 'code-refs solved-code');
  for (const ref of refs) {
    const file = files.get(ref.path);
    if (typeof file?.solution !== 'string') continue;
    const found = span(ref.lines), all = file.solution.split('\n');
    const first = found ? found.first : 1, last = found ? found.last : all.length;
    const card = node('figure', 'code-ref');
    const caption = append(node('figcaption', 'code-ref-head'), icon(ICON.file), append(node('span', 'code-ref-path'), node('bdi', '', ref.path)), node('span', 'code-ref-lines', first === last ? `line ${first}` : `lines ${first}–${last}`));
    caption.append(button('Open solved file', () => openInWorkspace(ref.path, ref.lines, { solution: true }), 'quiet code-ref-open'));
    const listing = renderCode(all.slice(first - 1, last).join('\n'), file.language || ref.path.split('.').pop(), { numbers: true, start: first });
    card.append(caption, listing);
    if (ref.walkthrough?.length) card.append(codeNotes(ref.walkthrough, listing, first));
    box.append(card);
  }
  return box;
}
