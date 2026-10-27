import data from './data.mjs';
import { node, button } from './dom.mjs';

const expandedCategories = new Set();

// A pooled item keeps its source identity: selection and order never change progress keys.
export function itemKey(unit, item) {
  const owner = item.origin || unit;
  return `${owner.key}:${owner.revision}:${item.key}`;
}
// keep(kind, itemKey) narrows the pool, for example to items marked for review.
export function revisionDeck(selected, keep = () => true) {
  const units = data.units.filter(unit => selected.has(unit.key));
  const collect = kind => units.flatMap(unit => unit[kind].map(item => ({
    ...item, origin: { key: unit.key, revision: unit.revision, title: unit.title },
  })).filter(item => keep(kind, itemKey(unit, item))));
  return { key: 'revision', title: 'Revision', flashcards: collect('flashcards'), questions: collect('questions') };
}
export function topicPicker(selected, change) {
  const root = node('details', 'disclosure revision-topics'); root.open = selected.size === 0;
  const summary = node('summary');
  const controls = node('div', 'cluster');
  const group = node('fieldset', 'topic-options');
  group.append(node('legend', 'visually-hidden', 'Revision topics'));
  const inputs = [], folders = new Map();
  function sync() {
    summary.textContent = `Topics · ${selected.size} / ${data.units.length}`;
    for (const { input, keys } of inputs) {
      const count = [...keys].filter(key => selected.has(key)).length;
      input.checked = count === keys.size;
      input.indeterminate = count > 0 && count < keys.size;
    }
    for (const { keys, counter } of folders.values()) {
      counter.textContent = `${[...keys].filter(key => selected.has(key)).length} / ${keys.size}`;
    }
  }
  function changed() { sync(); change(); }
  function checkbox(label, keys, name, kind) {
    const input = node('input'); input.type = 'checkbox';
    input.setAttribute('aria-label', name); input.dataset.selection = kind;
    input.addEventListener('change', () => {
      for (const key of keys) { if (input.checked) selected.add(key); else selected.delete(key); }
      changed();
    });
    inputs.push({ input, keys }); label.append(input); return input;
  }
  controls.append(button('Select all', () => {
    data.units.forEach(unit => selected.add(unit.key)); changed();
  }, 'quiet'), button('Clear', () => { selected.clear(); changed(); }, 'quiet'));
  for (const unit of data.units) {
    let parent = group;
    const ancestry = unit.path || [];
    ancestry.forEach((name, depth) => {
      const path = ancestry.slice(0, depth + 1), key = JSON.stringify(path);
      if (!folders.has(key)) {
        const folder = node('div', 'topic-category'), keys = new Set();
        const heading = node('div', 'topic-category-heading');
        const label = node('label', 'topic-option topic-category-label');
        checkbox(label, keys, `Category: ${path.join(' / ')}`, 'category');
        label.append(node('span', '', name));
        const children = node('div', 'topic-children');
        children.id = `revision-category-${folders.size}`;
        const toggle = button('', () => {
          if (children.hidden) expandedCategories.add(key); else expandedCategories.delete(key);
          update();
        }, 'icon-button quiet topic-category-toggle');
        toggle.dataset.topicToggle = 'true';
        toggle.setAttribute('aria-controls', children.id);
        const counter = node('span', 'small topic-category-count');
        function update() {
          children.hidden = !expandedCategories.has(key);
          toggle.setAttribute('aria-expanded', String(!children.hidden));
          const title = `${children.hidden ? 'Expand' : 'Collapse'} ${path.join(' / ')}`;
          toggle.setAttribute('aria-label', title); toggle.title = title;
        }
        update(); heading.append(toggle, label, counter);
        folder.append(heading, children); parent.append(folder);
        folders.set(key, { children, keys, counter });
      }
      const folder = folders.get(key); folder.keys.add(unit.key); parent = folder.children;
    });
    const label = node('label', 'topic-option');
    checkbox(label, new Set([unit.key]), unit.title, 'topic');
    const text = node('span'); text.append(node('span', '', unit.title));
    if (!ancestry.length) text.append(node('span', 'small', unit.label));
    label.append(text); parent.append(label);
  }
  sync();
  root.append(summary, controls, group); return root;
}
