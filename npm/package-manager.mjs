import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { copyFile, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { acquireLock } from './lock.mjs';
import { installationTarget, npmCli, packageName, packageStorage, runNpm } from './npm-command.mjs';

function runLauncher(root, args, quiet = false) {
  const result = spawnSync(process.execPath, [join(root, 'npm/tum-mcp.mjs'), ...args], {
    stdio: quiet ? ['ignore', 'pipe', 'pipe'] : 'inherit', encoding: 'utf8', shell: false, timeout: 600000,
  });
  if (result.error || result.status !== 0) {
    if (quiet) process.stderr.write((result.stdout || '') + (result.stderr || ''));
    throw new Error(`${args[0]} did not complete. Saved data and customized client files were preserved; review the details and retry.`);
  }
}

function versionParts(version) {
  const match = typeof version === 'string' && version.match(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*))?(?:\+[\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*)?$/);
  if (!match) throw new Error('npm returned an invalid package version.');
  const prerelease = match[4]?.split('.') || [];
  if (prerelease.some(part => /^0\d+$/.test(part))) throw new Error('npm returned an invalid prerelease version.');
  return { core: match.slice(1, 4).map(BigInt), prerelease };
}

export function newerVersion(latest, current) {
  const left = versionParts(latest), right = versionParts(current);
  for (let i = 0; i < left.core.length; i++) if (left.core[i] !== right.core[i]) return left.core[i] > right.core[i];
  const a = left.prerelease, b = right.prerelease;
  if (!a.length || !b.length) return !a.length && Boolean(b.length);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] === undefined) return false;
    if (b[i] === undefined) return true;
    if (a[i] === b[i]) continue;
    const numericA = /^\d+$/.test(a[i]), numericB = /^\d+$/.test(b[i]);
    if (numericA && numericB) return BigInt(a[i]) > BigInt(b[i]);
    if (numericA !== numericB) return numericB;
    return a[i] > b[i];
  }
  return false;
}

async function operate(job) {
  const release = await acquireLock(job.target.prefix, 'tum-mcp-package');
  try {
    const scope = ['--prefix', job.target.prefix, `--global=${job.target.global}`];
    if (job.action === 'uninstall') {
      const configured = existsSync(join(job.dataDirectory, 'runtime.json')) ||
        existsSync(join(job.configDirectory, 'clients'));
      if (configured || job.args.some(arg => ['--purge-runtime', '--forget-credentials'].includes(arg))) {
        runLauncher(job.root, ['uninstall', '--keep-package', ...job.args]);
      }
      runNpm(job.npm, ['uninstall', ...scope, packageName]);
      console.log('TUM MCP package and managed client setup removed. Saved user data was retained unless explicitly requested.');
      return;
    }
    const current = JSON.parse(readFileSync(join(job.root, 'package.json'), 'utf8')).version;
    const latest = JSON.parse(runNpm(job.npm, ['view', `${packageName}@latest`, 'version', '--json', ...scope], true));
    if (!newerVersion(latest, current)) {
      console.log(`Installed ${current}; no newer npm release. Refreshing configured clients.`);
      runLauncher(job.root, ['update', '--local']);
      return;
    }
    console.log(`Preparing TUM MCP ${latest}.`);
    const packed = JSON.parse(runNpm(job.npm, ['pack', `${packageName}@${latest}`, '--pack-destination', job.temporary, '--json', ...scope], true));
    if (!Array.isArray(packed) || packed.length !== 1 || packed[0].name !== packageName || packed[0].version !== latest || basename(packed[0].filename) !== packed[0].filename) {
      throw new Error('npm package metadata did not match the selected release.');
    }
    const archive = join(job.temporary, packed[0].filename);
    const staging = join(job.temporary, 'prepared');
    runNpm(job.npm, ['install', '--prefix', staging, '--global=false', archive], true);
    const prepared = join(staging, 'node_modules', packageName);
    runLauncher(prepared, ['setup'], true);
    // Only a healthy prepared release may replace the user's npm installation.
    runNpm(job.npm, ['install', ...scope, job.target.global ? archive : `${packageName}@${latest}`]);
    if (JSON.parse(readFileSync(join(job.root, 'package.json'), 'utf8')).version !== latest) throw new Error('npm did not install the selected version; client activation was stopped.');
    runLauncher(job.root, ['update', '--local']);
    console.log(`Updated TUM MCP to ${latest}. Restart clients to load refreshed skills.`);
  } finally { await release(); }
}

export async function managePackage(action, args, dataDirectory) {
  const root = dirname(dirname(fileURLToPath(import.meta.url)));
  const inside = relative(root, process.cwd());
  if (inside === '' || (inside.split(sep)[0] !== '..' && !isAbsolute(inside))) throw new Error('Run package update/removal from outside the installed package directory.');
  const target = installationTarget(root);
  const storage = packageStorage(root, dataDirectory);
  const configDirectory = storage.TUM_MCP_CONFIG_DIR;
  const npm = npmCli();
  const temporary = await mkdtemp(join(tmpdir(), 'tum-mcp-package-'));
  try {
    for (const name of ['package-manager.mjs', 'npm-command.mjs', 'lock.mjs']) await copyFile(join(root, 'npm', name), join(temporary, name));
    const job = { action, args, root, dataDirectory, configDirectory, target, npm, temporary };
    const path = join(temporary, 'job.json');
    await writeFile(path, JSON.stringify(job), { mode: 0o600, flag: 'wx' });
    // This worker and its cwd survive Windows replacing/removing the package files.
    const result = spawnSync(process.execPath, [join(temporary, 'package-manager.mjs'), '--job', path], {
      cwd: temporary, stdio: 'inherit', shell: false, env: { ...process.env, ...storage },
    });
    return result.status ?? (result.signal === 'SIGINT' ? 130 : 2);
  } finally { await rm(temporary, { recursive: true, force: true }); }
}

if (process.argv[1] && process.argv[2] === '--job' && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { await operate(JSON.parse(readFileSync(process.argv[3], 'utf8'))); }
  catch (error) { console.error(error.message); process.exitCode = 2; }
}
