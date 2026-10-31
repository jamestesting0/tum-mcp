import data from './data.mjs';

export const exercisePrefix = `course-exercises:${data.course.identity}:`;
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const text = value => typeof value === 'string' ? value.slice(0, 64000) : '';

export function exerciseState(read, write, prefix = exercisePrefix) {
  const cache = new Map();
  function get(exercise) {
    const key = `${prefix}${exercise.key}:${exercise.revision}`;
    if (!cache.has(key)) {
      const saved = object(read(key, {})), steps = {};
      for (const step of exercise.steps) {
        const previous = object(object(saved.steps)[step.key]);
        steps[step.key] = { draft: text(previous.draft),
          hints: Number.isInteger(previous.hints) ? Math.max(0, Math.min(step.hints.length, previous.hints)) : 0,
          checked: typeof previous.checked === 'string' ? text(previous.checked) : null,
          compared: previous.compared === true, skipped: previous.skipped === true,
          first: object(previous.first), latest: object(previous.latest) };
      }
      const partSolutions = Object.fromEntries((exercise.parts || []).map(part => {
        const previous = object(object(saved.partSolutions)[part]);
        return [part, { open: previous.open === true, viewed: previous.viewed === true }];
      }));
      cache.set(key, { key, revision: exercise.revision, steps, partSolutions,
        helpOpen: saved.helpOpen === true, solutionOpen: saved.solutionOpen === true,
        solutionViewed: saved.solutionViewed === true, lastStep: saved.lastStep || exercise.steps[0].key });
    }
    return cache.get(key);
  }
  function save(exercise) {
    const value = get(exercise);
    const latest = read(`${prefix}${exercise.key}:latest`, null);
    if (typeof latest === 'string' && latest !== exercise.revision && /^[a-f0-9]{64}$/.test(latest))
      write(`${prefix}${exercise.key}:previous`, latest);
    write(value.key, value);
    write(`${prefix}${exercise.key}:latest`, exercise.revision);
  }
  function attempt(exercise, step, correct = null) {
    const value = get(exercise), state = value.steps[step.key];
    const viewed = step.part && exercise.part_blocks?.[step.part]
      ? value.partSolutions[step.part].viewed : value.solutionViewed;
    const summary = { value: state.draft, correct, hints: state.hints, solutionViewed: viewed };
    if (!Object.keys(state.first).length) state.first = summary;
    state.latest = summary; save(exercise);
  }
  return { get, save, attempt, clear: () => cache.clear() };
}
