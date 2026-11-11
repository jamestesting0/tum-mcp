import { createAppEmbed } from './app/embed.js';
import { cliFrames } from './content/cli.js';
import { PACE, chatAt, stepPlan } from './story/play.js';
import { terminalView } from './ui/terminal.js';
import { createTerminalApp } from './hosts/terminal-app.js';
import { createSignin } from './hosts/signin.js';
import { createWorkbench } from './hosts/workbench.js';
import { h, replace, slice } from './ui/dom.js';
import { stroke } from './ui/icons.js';

const DESK = { width: 1280, height: 800 };
const PRELOAD_CHAPTER = 3;

const leading = beats => {
  let index = -1;
  while (beats[index + 1] && (beats[index + 1].opens || beats[index + 1].route)) index += 1;
  return index;
};

export function createStage({ root, story, timeline, marks, appDocument }) {
  const desk = h('div.desk');
  const hostSlot = h('div.host-slot');
  const address = h('span.bw-address', {}, h('span', { text: '127.0.0.1:8765' }));
  const browser = h('div.bw', { 'aria-hidden': 'true' },
    h('div.bw-bar', {}, h('span.traffic', {}, h('i'), h('i'), h('i')),
      h('span.bw-nav', {}, stroke('back', 16), stroke('forward', 16)), address, h('span.bw-nav', {}, stroke('reload', 15))));
  const embed = createAppEmbed({
    documentText: appDocument,
    stage: root,
    onEngage: engaged => {
      browser.setAttribute('aria-hidden', String(!engaged && !browser.classList.contains('is-open')));
      if (!engaged && lastRender) render(...lastRender);
    },
  });
  browser.append(embed.element);
  const signin = createSignin();
  desk.append(hostSlot, signin.element, browser);
  replace(root, desk);
  root.tabIndex = -1;

  const hosts = new Map();
  let hostKey = story.hosts[0].key;
  let current = null;
  let lastRender = null;

  function instance(key) {
    if (!hosts.has(key)) hosts.set(key, key === 'claude' ? createTerminalApp({ marks }) : createWorkbench(key, { marks }));
    return hosts.get(key);
  }

  function setHost(key) {
    hostKey = key;
    current = instance(key);
    replace(hostSlot, current.element);
    root.dataset.host = key;
    if (lastRender) render(...lastRender);
  }

  const framesFor = new Map();
  const frames = () => {
    if (!framesFor.has(hostKey)) framesFor.set(hostKey, cliFrames(hostKey));
    return framesFor.get(hostKey);
  };
  const plan = step => stepPlan(step, frames());

  // `ms` is how far the step has played by itself; `beat` is the guide beat the scroll asks for.
  function render(step, ms, beat = -1) {
    lastRender = [step, ms, beat];
    const steps = plan(step);
    const played = step.chat ? chatAt(step, steps, ms) : { chatCount: step.state.chat.length, filesCount: step.state.files.length, composeFraction: 1 };
    const compose = step.chat?.compose ?? null;
    const command = story.hosts.find(host => host.key === hostKey).command;
    const files = step.state.files.slice(0, played.filesCount);
    const previousFiles = new Set(step.previous.files);
    const view = {
      course: story.course,
      command,
      focus: step.focus,
      folder: step.state.folder,
      terminal: step.state.terminal ? terminalView(step.state.terminal.blocks, frames(), step.terminal ? ms : Number.POSITIVE_INFINITY) : null,
      terminalKey: `${step.index}`,
      terminalStep: Boolean(step.terminal),
      chat: step.state.chat.slice(0, played.chatCount),
      chatCount: played.chatCount,
      compose: compose ? { text: slice(compose.replace('{command}', command), played.composeFraction), caret: true } : { text: '', caret: false },
      files,
      fresh: new Set(files.filter(path => !previousFiles.has(path))),
      editor: step.editor && files.includes(step.editor) ? step.editor : step.previous.editor,
    };
    current.update(view);
    root.dataset.focus = step.focus;
    const browsing = steps.browser ? (ms - steps.browser.at) / steps.browser.duration : -1;
    signin.update(browsing >= 0 && browsing < 1 ? browsing : null);

    const appOpen = step.state.app != null && ms >= steps.appAt;
    browser.classList.toggle('is-open', appOpen);
    if (!embed.engaged) browser.setAttribute('aria-hidden', String(!appOpen));
    if (step.chapterIndex >= PRELOAD_CHAPTER) embed.load();
    // The app is prepared for the scene while its window is still closed, so it opens on the
    // right page; beats wait until the window has finished opening.
    if (step.state.app != null && step.chapterIndex >= PRELOAD_CHAPTER) {
      const beats = step.app ? step.guide ?? [] : [];
      const ready = appOpen && ms >= steps.appAt + (steps.appAt ? PACE.appOpen : 0);
      embed.show(step.state.app, {
        key: step.key,
        start: step.app ? step.appStart ?? null : null,
        scroll: step.app ? step.appScroll ?? null : null,
        beats,
        // The switch into the scene's page (its leading menu and page-change clicks) plays by itself
        // once the app is ready; the scroll paces only the beats that show the page.
        beat: ready ? Math.min(Math.max(beat, leading(beats)), beats.length - 1) : -1,
      });
    }
  }

  function layout() {
    const box = root.getBoundingClientRect();
    const scale = Math.min(box.width / DESK.width, box.height / DESK.height);
    root.style.setProperty('--desk-scale', String(scale));
  }

  addEventListener('resize', layout);
  new ResizeObserver(layout).observe(root);
  setHost(hostKey);
  layout();

  return { setHost, render, embed, plan, preload: () => embed.load() };
}
