import data from './data.mjs';

export const exercisePrefix = `course-exercises:${data.course.identity}:`;
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const text = value => typeof value === 'string' ? value.slice(0, 64000) : '';

export function exerciseState(read, write) {
  const cache = new Map();
  function get(exercise) {
    const key = `${exercisePrefix}${exercise.key}:${exercise.revision}`;
    if (!cache.has(key)) {
      const saved = object(read(key, {})), steps = {};
      for (const step of exercise.steps) {
        const previous = object(object(saved.steps)[step.key]);
        steps[step.key] = { draft: text(previous.draft),
          hints: Number.isInteger(previous.hints) ? Math.max(0, Math.min(step.hints.length, previous.hints)) : 0,
          checked: typeof previous.checked === 'string' ? text(previous.checked) : null,
          compared: previous.compared === true, revealed: previous.revealed === true, skipped: previous.skipped === true,
          first: object(previous.first), latest: object(previous.latest) };
      }
      cache.set(key, { key, revision: exercise.revision, steps,
        started: saved.started === true, reviewed: saved.reviewed === true,
        helpOpen: saved.helpOpen === true, solutionOpen: saved.solutionOpen === true,
        solutionViewed: saved.solutionViewed === true, lastStep: saved.lastStep || exercise.steps[0].key });
    }
    return cache.get(key);
  }
  function save(exercise) {
    const value = get(exercise);
    const latest = read(`${exercisePrefix}${exercise.key}:latest`, null);
    if (typeof latest === 'string' && latest !== exercise.revision && /^[a-f0-9]{64}$/.test(latest))
      write(`${exercisePrefix}${exercise.key}:previous`, latest);
    write(value.key, value);
    write(`${exercisePrefix}${exercise.key}:latest`, exercise.revision);
  }
  function attempt(exercise, step, correct = null) {
    const value = get(exercise), state = value.steps[step.key];
    const summary = { value: state.draft, correct, hints: state.hints, stepReasoning: state.revealed, solutionViewed: value.solutionViewed };
    if (!Object.keys(state.first).length) state.first = summary;
    state.latest = summary; save(exercise);
  }
  function status(exercise) {
    const value = get(exercise);
    return value.reviewed ? 'Reviewed' : value.started ? 'In progress' : 'Not started';
  }
  return { get, save, attempt, status, clear: () => cache.clear() };
}
