import data from './data.mjs';

export function commentStore() {
  let document = null, pending = Promise.resolve(), loading = null;
  async function request(options) {
    let response;
    try { response = await fetch('/_study/comments', { cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(10000), ...options }); }
    catch { throw new Error('Preview unavailable. Retry.'); }
    if (response.status === 304 && document) return document;
    let value;
    try { value = await response.json(); } catch { throw new Error('Comments unavailable. Use the local preview.'); }
    if (!response.ok) {
      const failure = new Error(value.error || 'Save failed. Retry.');
      failure.conflict = response.status === 409; throw failure;
    }
    if (value.course_identity !== data.course.identity || !Array.isArray(value.comments) || typeof value.revision !== 'string') {
      throw new Error('Course mismatch. Reload the preview.');
    }
    if (document?.revision === value.revision) return document;
    document = value; return document;
  }
  function enqueue(options) {
    const task = pending.then(() => request(options)); pending = task.catch(() => {}); return task;
  }
  function load() {
    if (!loading) loading = enqueue({ headers: document ? { 'If-None-Match': `"${document.revision}"` } : {} }).finally(() => { loading = null; });
    return loading;
  }
  return {
    get value() { return document; },
    load,
    async change(operation, baseline) {
      if (!document) await load();
      const original = baseline || document.comments.find(item => item.id === operation.id);
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
      const conflict = () => Object.assign(new Error('Changed elsewhere.'), { conflict: true });
      for (let attempt = 0; attempt < 2; attempt++) {
        const current = document.comments.find(item => item.id === operation.id);
        if (operation.op === 'create' && current) {
          if (current.text === operation.text && Object.entries(operation.anchor).every(([key, value]) => current.anchor[key] === value)) return document;
          throw conflict();
        }
        if (operation.op !== 'create' && (!current || !same(current, original))) throw conflict();
        try {
          return await enqueue({ method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...operation, course_identity: data.course.identity, expected_revision: document.revision }) });
        } catch (failure) {
          if (!failure.conflict) throw failure;
          await load();
          if (attempt === 1) throw conflict();
        }
      }
    },
  };
}
