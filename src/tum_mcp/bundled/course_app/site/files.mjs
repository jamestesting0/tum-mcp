import data from './data.mjs';
import { node, svgNode, button, append } from './dom.mjs';
import { renderCode, codeEditor, languageName, lineSet } from './code.mjs';

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
const storage = key => `course-app:${data.course.identity}:files:v1:${key}`;
function readDrafts(key) {
  try { const value = JSON.parse(localStorage.getItem(storage(key)) || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  catch { return {}; }
}

// Ask the project on this page that holds `path` to open it, optionally at `lines`.
export function openInWorkspace(path, lines) {
  const target = [...document.querySelectorAll('.project')].find(item => item.workspace?.has(path));
  if (!target) return false;
  target.workspace.open(path, lines);
  target.scrollIntoView({ block: 'start', behavior: 'smooth' });
  return true;
}

export function renderFiles(block) {
  const files = new Map(block.files.map(file => [file.path, file]));
  const drafts = readDrafts(block.key);
  const content = path => typeof drafts[path] === 'string' ? drafts[path] : files.get(path).code;
  const save = () => { try { localStorage.setItem(storage(block.key), JSON.stringify(drafts)); } catch { /* storage blocked: drafts last for this visit */ } };
  const root = node('div', 'project'); root.dataset.workspace = block.key;
  root.setAttribute('role', 'region'); root.setAttribute('aria-label', `Code workspace: ${block.description}`);
  const start = block.open || block.files.find(file => file.editable)?.path || block.files[0].path;
  let open = [start], active = start, marked = new Set();

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
      const control = button('', () => { show(file.path); if (narrow.matches) setTree(false); }, 'project-file');
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
  // The file tree folds away on any width; phones start with it folded.
  function setTree(open) {
    treePanel.hidden = !open; body.classList.toggle('tree-hidden', !open);
    treeToggle.setAttribute('aria-expanded', String(open));
    treeToggle.setAttribute('aria-label', open ? 'Hide files' : 'Show files'); treeToggle.title = open ? 'Hide files' : 'Show files';
  }
  const syncNarrow = () => setTree(!narrow.matches);
  narrow.addEventListener('change', () => { if (root.isConnected) syncNarrow(); });

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
    if (file.editable && typeof drafts[file.path] === 'string' && drafts[file.path] !== file.code) {
      pathBar.append(button('Reset file', () => { delete drafts[file.path]; save(); paint(); }, 'quiet project-reset'));
    }
  }
  function paintPane(file) {
    pane.replaceChildren();
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
  function show(path, lines) {
    if (!open.includes(path)) open = [...open, path].slice(-6);
    active = path; marked = lineSet(lines); paint();
    const first = pane.querySelector('.code-line.marked');
    pane.scrollTop = first ? Math.max(0, first.getBoundingClientRect().top - pane.getBoundingClientRect().top - pane.clientHeight / 3) : 0;
  }
  root.workspace = { has: path => files.has(path), open: (path, lines) => show(path, lines) };
  syncNarrow(); paint();
  return root;
}

// What a step points at: the file, the lines, and a jump into the project above.
export function codeReferences(refs, files) {
  const box = node('div', 'code-refs');
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
    card.append(caption, renderCode(excerpt, file.language || ref.path.split('.').pop(), { numbers: true, start: first }));
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
