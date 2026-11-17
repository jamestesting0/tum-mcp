import data from '../../data.mjs';
import { node, button, append } from './dom.mjs';
import { renderFiles, fileIcon } from './files.mjs';
import { askButton } from '../ask/ask.mjs';

// A coding exercise as an editor: files, the code and the task side by side, as in the
// Artemis online editor. Files and Task fold away and resize by their dividers; each
// course remembers the layout. Narrow pages show one panel at a time.
const TASK = { min: 340, start: 400, share: 0.5 };
const EDITOR_MIN = 420, WIDE = 1100, NARROW = 760;
const prefsKey = `course-app:${data.course.identity}:ide:v1`;
const viewKey = key => `course-app:${data.course.identity}:ide-view:v1:${key}`;
function read(key, fallback) {
  try { const value = JSON.parse(localStorage.getItem(key)); return value ?? fallback; } catch { return fallback; }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage blocked: this visit only */ }
}

export function editorWorkspace({ block, task, exerciseKey, stepLabel }) {
  const prefs = read(prefsKey, {});
  const ide = node('div', 'ide');
  let size = 'wide', view = read(viewKey(exerciseKey), 'task');
  let taskOpen = prefs.taskOpen !== false, taskWidth = prefs.taskWidth || TASK.start;
  // A remembered tree wins; a first visit opens it only where three panels fit.
  let treeWanted = prefs.treeOpen;
  const save = change => { Object.assign(prefs, change); write(prefsKey, prefs); };

  const project = renderFiles(block, {
    treeWidth: prefs.treeWidth, treeOpen: false,
    onTreeWidth: width => save({ treeWidth: width }),
    onOpen: () => { if (size === 'narrow') setView('code'); },
  });

  // One control per panel. Opening the tree where it does not fit beside an open task folds
  // the task; opening the task folds the tree, which comes back when the task folds again.
  const filesToggle = button('', () => {
    treeWanted = !project.workspace.treeOpen; save({ treeOpen: treeWanted });
    if (treeWanted && taskOpen && !treeFits(true)) { taskOpen = false; save({ taskOpen }); }
    layout();
  }, 'quiet ide-toggle ide-files-toggle');
  filesToggle.append(fileIcon('tree'), node('span', '', 'Files'));
  const taskToggle = button('', () => { taskOpen = !taskOpen; save({ taskOpen }); layout(); }, 'quiet ide-toggle ide-task-toggle');
  const taskStep = node('span', 'ide-toggle-step');
  taskToggle.append(fileIcon('task'), node('span', '', 'Task'), taskStep);
  const bar = append(node('div', 'ide-bar'), filesToggle);
  if (block.origin === 'rebuilt') bar.append(node('span', 'ide-origin', 'Built from the problem statement'));
  // Narrow pages switch between the three panels instead.
  const views = node('div', 'ide-views'); views.setAttribute('role', 'tablist'); views.setAttribute('aria-label', 'Panel');
  const viewButtons = new Map(['files', 'code', 'task'].map(name => {
    const choice = button({ files: 'Files', code: 'Code', task: 'Task' }[name], () => setView(name), 'ide-view');
    choice.setAttribute('role', 'tab'); views.append(choice);
    return [name, choice];
  }));
  bar.append(node('span', 'ide-spacer'), views, taskToggle);
  // The corner Ask agent button would cover this bar, so the bar carries its own.
  const ask = askButton('ide-toggle ide-ask'); if (ask) bar.append(ask);

  const code = append(node('div', 'ide-code'), project);
  const divider = node('div', 'ide-divider');
  divider.setAttribute('role', 'separator'); divider.setAttribute('aria-orientation', 'vertical');
  divider.setAttribute('aria-label', 'Resize task'); divider.tabIndex = 0;
  const panel = append(node('div', 'ide-task'), task); panel.setAttribute('role', 'complementary'); panel.setAttribute('aria-label', 'Task');
  const body = append(node('div', 'ide-body'), code, divider, panel);
  ide.append(bar, body);

  const maxTask = () => Math.max(TASK.min, Math.min(ide.clientWidth * TASK.share, ide.clientWidth - EDITOR_MIN));
  function setTask(width, remember) {
    taskWidth = Math.round(Math.min(maxTask(), Math.max(TASK.min, width)));
    ide.style.setProperty('--task-width', `${taskWidth}px`);
    divider.setAttribute('aria-valuemin', String(TASK.min)); divider.setAttribute('aria-valuemax', String(Math.round(maxTask())));
    divider.setAttribute('aria-valuenow', String(taskWidth));
    if (remember) save({ taskWidth });
  }
  divider.addEventListener('pointerdown', event => {
    divider.setPointerCapture(event.pointerId);
    const right = ide.getBoundingClientRect().right;
    const move = moved => setTask(right - moved.clientX, false);
    divider.addEventListener('pointermove', move);
    divider.addEventListener('pointerup', () => { divider.removeEventListener('pointermove', move); setTask(taskWidth, true); }, { once: true });
  });
  divider.addEventListener('keydown', event => {
    const step = { ArrowLeft: 16, ArrowRight: -16 }[event.key];
    if (step) { event.preventDefault(); setTask(taskWidth + step, true); }
  });
  divider.addEventListener('dblclick', () => setTask(TASK.start, true));

  function setView(name) {
    view = name; write(viewKey(exerciseKey), name); layout();
  }
  // The tree needs 160px beside the editor and, when open, the task and its divider.
  const treeFits = withTask => ide.clientWidth - (withTask ? taskWidth + 5 : 0) - EDITOR_MIN >= 160;
  const showStep = () => { taskStep.textContent = taskOpen ? '' : stepLabel(); taskStep.hidden = !taskStep.textContent; };
  function layout() {
    const width = ide.clientWidth;
    size = width >= WIDE ? 'wide' : width >= NARROW ? 'medium' : 'narrow';
    ide.dataset.size = size; ide.dataset.view = view;
    const single = block.files.length < 2;
    // The tree yields first when the editor and an open task panel do not fit beside it.
    const tree = size === 'narrow' ? view === 'files' : !single && (treeWanted ?? size === 'wide') && treeFits(taskOpen);
    project.workspace.setTree(tree);
    ide.dataset.files = tree ? 'open' : 'closed';
    ide.dataset.task = size === 'narrow' || taskOpen ? 'open' : 'closed';
    filesToggle.hidden = single || size === 'narrow';
    filesToggle.setAttribute('aria-expanded', String(tree));
    taskToggle.hidden = size === 'narrow'; taskToggle.setAttribute('aria-expanded', String(taskOpen));
    viewButtons.get('files').hidden = single;
    for (const [name, choice] of viewButtons) choice.setAttribute('aria-selected', String(name === view));
    showStep();
    if (size !== 'narrow') setTask(taskWidth, false);
  }
  new ResizeObserver(() => { if (ide.isConnected) layout(); }).observe(ide);
  task.addEventListener('study-activity-change', showStep);
  ide.ide = {
    // "Open in files" and Compare's solved file bring the code into view on narrow pages.
    reveal(name) { if (size === 'narrow' && view !== name) setView(name); },
    open: (path, lines) => project.workspace.open(path, lines),
  };
  queueMicrotask(layout);
  return ide;
}
