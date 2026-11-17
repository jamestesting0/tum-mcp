// The Ask agent demo, run inside the tour's app frame before the app. It answers the local
// preview's agent API from a script, so the tour shows the real panel, its working log and an
// edit applied in place without an account. The study app itself runs unchanged.
(() => {
  const demo = JSON.parse(document.getElementById('ask-demo').textContent);
  const API = '/_study/agent/';
  // Ask agent is desktop-only in the app; the demo shows it on phones too.
  const media = window.matchMedia.bind(window);
  window.matchMedia = query => (query.trim() === '(pointer: coarse)' ? media('not all') : media(query));

  // The course data module hands its object to the frame (see app-document.mjs). The first edit
  // keeps a copy of it, and the edited course is that copy with the agent's step added.
  let original = null;
  let edited = false;
  let chat = null;
  const course = () => original ?? globalThis.__walkthroughData;
  const editedCourse = () => {
    const copy = structuredClone(original);
    copy.units.find(unit => unit.key === demo.unit).blocks[demo.block].steps.push(demo.step);
    Object.assign(copy.inlineMath, demo.math);
    return copy;
  };
  // The tour reloads the frame after the demo ran, so a scene played again starts afresh; a silent
  // rebuild plays the stream at once.
  const state = { instant: false, get used() { return chat !== null; } };
  window.__askDemo = state;

  const json = (value, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }));
  const efforts = ['low', 'medium', 'high', 'xhigh', 'max'];
  const status = {
    token: 'walkthrough',
    provider: 'claude',
    profile: 'claude-subscription',
    profiles: [{ id: 'claude-subscription', provider: 'claude', method: 'Max plan' }],
    providers: {
      claude: { installed: true, connected: true, method: 'Max plan' },
      codex: { installed: false, connected: false },
      cursor: { installed: false, connected: false },
    },
    options: {
      models: [
        { id: 'opus', label: 'Opus 5.5', description: 'For complex work and everyday tasks', efforts, effort: 'medium', default: true, family: 'opus' },
        { id: 'sonnet', label: 'Sonnet 5.5', description: 'Most efficient for simpler tasks', efforts, effort: 'medium', default: false, family: 'sonnet' },
      ],
      model: 'opus',
      effort: 'medium',
    },
  };
  const steps = ['Reading the sources', `Reading ${demo.file}`, `Editing ${demo.file}`];
  const at = () => new Date().toISOString();
  const pieces = text => text.match(/\S+\s*/g) ?? [];

  function send(body) {
    const id = chat?.id ?? crypto.randomUUID();
    const started = Date.now();
    const encoder = new TextEncoder();
    // Waits follow animation frames, so the stream keeps its pace however the browser schedules timers.
    const pause = ms => new Promise(resolve => {
      const end = performance.now() + (state.instant ? 0 : ms);
      const wait = () => (performance.now() >= end ? resolve() : requestAnimationFrame(wait));
      wait();
    });
    const stream = new ReadableStream({
      async start(controller) {
        const put = event => controller.enqueue(encoder.encode(`${JSON.stringify(event)}\n`));
        put({ type: 'chat', id });
        put({ type: 'thinking', text: '' });
        await pause(1100);
        for (const piece of pieces(demo.note)) { put({ type: 'note', text: piece }); await pause(45); }
        for (const step of steps) { await pause(250); put({ type: 'status', text: step }); await pause(650); }
        original ??= structuredClone(globalThis.__walkthroughData);
        edited = true;
        for (const piece of pieces(demo.answer)) { put({ type: 'note', text: piece }); await pause(30); }
        put({ type: 'status', text: 'Checking the edit', after: true });
        await pause(700);
        const student = { role: 'student', text: body.text, at: at(), quote: body.quote ?? '', section: body.section ?? '', change: null, log: [], worked: 0 };
        const message = {
          role: 'agent',
          text: `${demo.answer}\n\n${demo.summary}`,
          at: at(),
          quote: '',
          section: '',
          change: { id: 'walkthrough', sections: [demo.section], summary: demo.summary, undone: false, undoable: true },
          log: [
            { kind: 'thinking', text: '', seconds: 1 },
            { kind: 'note', text: demo.note, seconds: 0 },
            ...steps.map(text => ({ kind: 'step', text, seconds: 0 })),
            { kind: 'step', text: 'Checking the edit', seconds: 0 },
          ],
          worked: Math.max(1, Math.round((Date.now() - started) / 1000)),
        };
        chat = { id, provider: 'claude', profile: 'claude-subscription', title: body.text, place: body.place ?? '', route: body.view?.route ?? '', anchor: body.anchor ?? null, context: '', created: at(), updated: at(), messages: [student, message] };
        put({ type: 'message', message });
        put({ type: 'done', edited: true });
        controller.close();
      },
    });
    return Promise.resolve(new Response(stream, { headers: { 'Content-Type': 'application/x-ndjson' } }));
  }

  function toggle(undone) {
    edited = !undone;
    const change = chat.messages.at(-1).change;
    Object.assign(change, { undone, undoable: !undone, redoable: undone });
    return json({ ok: true });
  }

  const next = window.fetch;
  window.fetch = (input, init = {}) => {
    const route = new URL(typeof input === 'string' ? input : input.url, 'https://app.invalid/').pathname;
    if (route === '/data.mjs' && original) return Promise.resolve(new Response(`export default ${JSON.stringify(edited ? editedCourse() : course())};\n`));
    if (!route.startsWith(API)) return next(input, init);
    const path = route.slice(API.length).split('/');
    const body = init.body ? JSON.parse(init.body) : {};
    if (path[0] === 'status') return json(status);
    if (path[0] === 'chats' && path.length === 1) return json({ chats: chat ? [{ id: chat.id, title: chat.title, place: chat.place, route: chat.route, updated: chat.updated }] : [] });
    if (path[0] === 'chats' && chat?.id === path[1]) {
      if (path[2] === 'undo') return toggle(true);
      if (path[2] === 'redo') return toggle(false);
      if (path[2] === 'interrupt') return json({ ok: true });
      return json(chat);
    }
    if (path[0] === 'send') return send(body);
    if (path[0] === 'settings') return json(status.options);
    return json({ error: 'Ask agent in the tour shows one example.' }, 404);
  };
})();
