export function buildTimeline(story) {
  const chapterIndex = new Map(story.chapters.map((chapter, index) => [chapter.key, index]));
  const steps = [];
  let state = { terminal: null, chat: [], files: [], editor: null, folder: false, app: null, appSince: null };
  let start = 0;
  for (const [index, step] of story.steps.entries()) {
    const chat = step.chat ?? {};
    const sent = chat.send ? [{ role: 'user', text: chat.send }] : [];
    const before = state;
    state = {
      terminal: step.terminal ?? (step.folder && !state.folder ? { blocks: [] } : state.terminal),
      chat: [...state.chat, ...sent, ...(chat.messages ?? [])],
      files: [...state.files, ...(chat.files ?? [])],
      editor: step.editor ?? state.editor,
      folder: step.folder ?? state.folder,
      app: step.app ?? state.app,
      appSince: state.appSince ?? (step.app ? index : null),
    };
    steps.push({
      ...step,
      index,
      chapterIndex: chapterIndex.get(step.chapter),
      start,
      state,
      added: { chat: sent.length + (chat.messages?.length ?? 0), files: chat.files?.length ?? 0 },
      previous: before,
    });
    start += step.weight;
  }
  const chapters = story.chapters.map(chapter => {
    const first = steps.find(step => step.chapter === chapter.key);
    return { ...chapter, start: first?.start ?? start };
  });
  return { steps, chapters, total: start };
}

export function locate(timeline, stepPosition) {
  const { steps } = timeline;
  let current = steps[0];
  for (const step of steps) if (stepPosition >= step.start) current = step;
  const local = Math.min(1, Math.max(0, (stepPosition - current.start) / current.weight));
  return { step: current, t: local };
}
