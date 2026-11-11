// Creates or refreshes the synthetic course project in website/course with the real CLI:
// `tum-mcp study init` on first run, `tum-mcp study sync` afterwards, then `tum-mcp study build`.
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { snapshot } from './course-sources.mjs';
import { paths } from './lib/paths.mjs';

const run = promisify(execFile);
const study = async (...args) => {
  const { stdout } = await run('uv', ['run', '--project', paths.repo, '--quiet', 'tum-mcp', 'study', ...args], {
    cwd: paths.repo, maxBuffer: 64 * 1024 * 1024,
  });
  return stdout.trim();
};

await mkdir(paths.course, { recursive: true });
const file = path.join(paths.course, '.tum-mcp', 'snapshot.json');
await mkdir(path.dirname(file), { recursive: true });
await writeFile(file, `${JSON.stringify(snapshot, null, 2)}\n`);
const initialized = existsSync(path.join(paths.course, '.tum-mcp', 'state.json'));
console.log(initialized
  ? await study('sync', paths.course, '--snapshot', file)
  : await study('init', paths.course, '--course', snapshot.course.title, '--snapshot', file, '--learner', 'off'));
if (process.argv.includes('--build')) console.log(await study('build', paths.course));
