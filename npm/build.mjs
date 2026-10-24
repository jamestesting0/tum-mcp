import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const destination = join(root, 'npm', 'backend');
mkdirSync(destination, { recursive: true });
mkdirSync(join(root, 'dist'), { recursive: true });
function run(args, quiet = false) {
  const result = spawnSync('uv', args, { cwd: root, stdio: ['ignore', quiet ? 'ignore' : 'inherit', 'inherit'], shell: false });
  if (result.error || result.status !== 0) throw new Error('Backend build failed; install uv and inspect the error above.');
}
run(['build', '--wheel', '--out-dir', destination]);
// uv creates a nested .gitignore containing '*'; npm must not inherit it here.
writeFileSync(join(destination, '.npmignore'), '');
run(['export', '--locked', '--no-dev', '--no-emit-project', '--no-header', '--format', 'requirements-txt', '--output-file', join(destination, 'requirements.txt')], true);
const wheels = readdirSync(destination).filter(name => name.endsWith('.whl'));
if (wheels.length !== 1) throw new Error('Expected exactly one backend wheel. Remove stale build artifacts.');
const integrity = name => createHash('sha256').update(readFileSync(join(destination, name))).digest('hex');
writeFileSync(join(destination, 'manifest.json'), JSON.stringify({
  wheel: wheels[0], wheelSha256: integrity(wheels[0]), requirementsSha256: integrity('requirements.txt'),
}, null, 2) + '\n');
