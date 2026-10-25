import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { mkdir, rename, rm, rmdir, writeFile } from 'node:fs/promises';
import { hostname } from 'node:os';
import { join } from 'node:path';

export async function acquireLock(root, name = 'setup') {
  await mkdir(root, { recursive: true, mode: 0o700 });
  const lock = join(root, `${name}.lock`);
  const owner = { pid: process.pid, host: hostname(), nonce: randomUUID() };
  const guard = join(root, `${name}.claim`);
  try { await mkdir(guard, { mode: 0o700 }); }
  catch { throw new Error(`Another ${name} is claiming the lock. Retry; an interrupted ${name}.claim needs local review.`); }
  try {
    try { await mkdir(lock, { mode: 0o700 }); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let previous;
      try { previous = JSON.parse(readFileSync(join(lock, 'owner.json'), 'utf8')); }
      catch { throw new Error(`${name} lock has no readable owner. Confirm no operation is running before removing ${name}.lock.`); }
      if (!Number.isSafeInteger(previous.pid) || previous.pid <= 0 || previous.host !== hostname()) {
        throw new Error(`${name} lock belongs to an unknown owner; preserve it for local review.`);
      }
      let alive = true;
      try { process.kill(previous.pid, 0); }
      catch (failure) { if (failure.code === 'ESRCH') alive = false; }
      if (alive) throw new Error(`Another ${name} is running; retry when it finishes.`);
      const abandoned = `${lock}.${randomUUID()}.abandoned`;
      await rename(lock, abandoned);
      await rm(abandoned, { recursive: true, force: true });
      try { await mkdir(lock, { mode: 0o700 }); }
      catch { throw new Error(`Another ${name} acquired the lock; retry when it finishes.`); }
    }
    const temporary = join(lock, `${owner.nonce}.pending`);
    await writeFile(temporary, JSON.stringify(owner), { mode: 0o600, flag: 'wx' });
    await rename(temporary, join(lock, 'owner.json'));
  } finally { await rmdir(guard); }
  return async () => {
    const current = JSON.parse(readFileSync(join(lock, 'owner.json'), 'utf8'));
    if (current.nonce !== owner.nonce) throw new Error(`${name} lock ownership changed; it was preserved.`);
    await rm(lock, { recursive: true, force: true });
  };
}
