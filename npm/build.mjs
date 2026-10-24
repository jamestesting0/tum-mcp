import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const destination = join(root, 'npm', 'backend');
mkdirSync(join(root, 'dist'), { recursive: true });
const staging = mkdtempSync(join(root, 'npm/.backend-build-'));
const backup = `${staging}-previous`;
function run(args, quiet = false) {
  const result = spawnSync('uv', args, { cwd: root, stdio: ['ignore', quiet ? 'ignore' : 'inherit', 'inherit'], shell: false });
  if (result.error || result.status !== 0) throw new Error('Backend build failed; install uv and inspect the error above.');
}
try {
  run(['build', '--wheel', '--out-dir', staging]);
  writeFileSync(join(staging, '.npmignore'), '');
  run(['export', '--locked', '--no-dev', '--no-emit-project', '--no-header', '--format', 'requirements-txt', '--output-file', join(staging, 'requirements.txt')], true);
  const wheels = readdirSync(staging).filter(name => name.endsWith('.whl'));
  const version = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version;
  if (wheels.length !== 1 || !wheels[0].includes(`-${version}-`)) throw new Error('Backend and npm package versions must match.');
  const integrity = name => createHash('sha256').update(readFileSync(join(staging, name))).digest('hex');
  writeFileSync(join(staging, 'manifest.json'), JSON.stringify({
    wheel: wheels[0], wheelSha256: integrity(wheels[0]), requirementsSha256: integrity('requirements.txt'),
  }, null, 2) + '\n');
  if (existsSync(destination)) renameSync(destination, backup);
  try { renameSync(staging, destination); }
  catch (error) { if (existsSync(backup)) renameSync(backup, destination); throw error; }
  rmSync(backup, { recursive: true, force: true });
} finally { rmSync(staging, { recursive: true, force: true }); }
