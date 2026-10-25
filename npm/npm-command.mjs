import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, dirname, join, basename, resolve, relative, isAbsolute, sep } from 'node:path';

export const packageName = '@jamestesting888/tum-mcp';

function canonical(value) {
  let path = resolve(value.replace(/^~(?=$|[/\\])/, homedir()));
  const tail = [];
  while (!existsSync(path)) { tail.unshift(basename(path)); path = dirname(path); }
  return join(realpathSync(path), ...tail);
}

export function packageStorage(root, dataDirectory) {
  const home = homedir();
  const base = process.platform === 'darwin' ? join(home, 'Library/Application Support')
    : process.platform === 'win32' ? process.env.LOCALAPPDATA || join(home, 'AppData/Local')
    : process.env.XDG_DATA_HOME || join(home, '.local/share');
  const storage = {
    TUM_MCP_DATA_DIR: canonical(dataDirectory),
    TUM_MCP_CONFIG_DIR: canonical(process.env.TUM_MCP_CONFIG_DIR || join(dataDirectory, 'config')),
    TUM_MOODLE_DATA_DIR: canonical(process.env.TUM_MOODLE_DATA_DIR || join(base, 'TUMMoodle')),
    TUM_MOODLE_DOWNLOAD_DIR: canonical(process.env.TUM_MOODLE_DOWNLOAD_DIR || join(home, 'Downloads/TUM Moodle')),
  };
  const config = storage.TUM_MCP_CONFIG_DIR;
  const settings = join(config, 'preferences.json');
  let workspace = join(home, 'University');
  if (existsSync(settings)) {
    try {
      const prefs = JSON.parse(readFileSync(settings, 'utf8'));
      if (prefs.workspace_root !== undefined) {
        if (typeof prefs.workspace_root !== 'string') throw new Error('Invalid storage path');
        workspace = prefs.workspace_root;
      }
    } catch { throw new Error('Storage settings could not be verified; package files and saved data were preserved.'); }
  }
  for (const path of [...Object.values(storage), workspace]) {
    const inside = relative(root, canonical(path));
    if (inside === '' || (inside.split(sep)[0] !== '..' && !isAbsolute(inside))) {
      throw new Error('Package installation overlaps saved data or course work. Move that data outside the package before update/removal.');
    }
  }
  return storage;
}

export function npmCli() {
  const paths = (process.env.PATH || '').split(delimiter);
  const candidates = [process.env.npm_execpath,
    join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js'),
    join(dirname(dirname(process.execPath)), 'lib/node_modules/npm/bin/npm-cli.js'),
    ...paths.flatMap(path => [join(path, 'npm'), join(path, 'node_modules/npm/bin/npm-cli.js')])];
  for (const path of candidates) {
    if (!path || !existsSync(path)) continue;
    const resolved = realpathSync(path);
    if (basename(resolved) !== 'npm-cli.js') continue;
    const manifest = join(dirname(dirname(resolved)), 'package.json');
    if (existsSync(manifest) && JSON.parse(readFileSync(manifest, 'utf8')).name === 'npm') return resolved;
  }
  throw new Error('npm could not be located beside Node or on PATH. Install Node.js with npm, then retry.');
}

export function runNpm(cli, args, capture = false) {
  const result = spawnSync(process.execPath, [cli, ...args, '--ignore-scripts', '--no-audit', '--no-fund', '--no-update-notifier'], {
    shell: false, stdio: capture ? ['ignore', 'pipe', 'inherit'] : 'inherit', encoding: 'utf8', timeout: 600000,
  });
  if (result.error || result.status !== 0) throw new Error('npm operation failed. Saved data and retained client runtimes were preserved; resolve the npm error and retry.');
  return capture ? result.stdout.trim() : '';
}

export function installationTarget(root) {
  const modules = dirname(dirname(root));
  if (basename(modules) !== 'node_modules' || modules.split(/[\\/]/).some(part => ['.pnpm', '_npx'].includes(part))) {
    throw new Error('Package management requires an npm installation. Use update --local for a source/pinned build.');
  }
  if (`${basename(dirname(root))}/${basename(root)}` !== packageName) {
    throw new Error('Automatic package management requires the original package name; aliases were preserved.');
  }
  const parent = dirname(modules);
  const prefix = process.platform === 'win32' ? parent : dirname(parent);
  const shim = process.platform === 'win32' ? join(prefix, 'tum-mcp.cmd') : join(prefix, 'bin/tum-mcp');
  if (existsSync(shim)) {
    const owned = process.platform === 'win32'
      ? readFileSync(shim, 'utf8').replaceAll('\\', '/').includes('node_modules/@jamestesting888/tum-mcp/npm/tum-mcp.mjs')
      : realpathSync(shim) === join(root, 'npm/tum-mcp.mjs');
    if (owned && (process.platform === 'win32' || basename(parent) === 'lib')) return { prefix, global: true };
  }
  const manifest = join(parent, 'package.json');
  if (existsSync(manifest)) {
    const project = JSON.parse(readFileSync(manifest, 'utf8'));
    if (['dependencies', 'devDependencies', 'optionalDependencies'].some(key => project[key]?.[packageName])) {
      return { prefix: parent, global: false };
    }
  }
  throw new Error('The npm installation prefix could not be verified; package files were preserved.');
}
