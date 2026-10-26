#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { acquireSetupLock, currentPython, dataRoot, ensureRuntime, removeRuntimeFiles } from './runtime.mjs';
import { managePackage } from './package-manager.mjs';

let args = process.argv.slice(2);
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
try {
  if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    console.log(`TUM MCP ${version}
Usage: tum-mcp COMMAND [OPTIONS]

  setup       Configure your coding client and managed runtime
  connect     Sign in to selected campus services
  status      Show saved connections
  discover    List accessible courses or channels
  doctor      Check installation and authentication
  update      Update the package and configured clients
  uninstall   Remove managed setup and the npm package
  logout      Remove one saved connection
  serve       Run the MCP server over stdio
  version     Show the installed version
  skills      Manage local workflow skills
  study       Prepare, preview and publish a course app

Use --help for options, for example: tum-mcp study build --help
Run setup to provision the managed backend, then connect to sign in.
Reads use your campus account permissions; no local scope selection is needed.`);
  } else if (['--version', 'version'].includes(args[0])) {
    console.log(version);
  } else if (['setup', 'update', 'uninstall'].includes(args[0]) && args.some(arg => ['--help', '-h'].includes(arg))) {
    const help = {
      update: 'Usage: tum-mcp update [--local]\nInstall the latest npm release and refresh configured clients.\n--local refreshes this installed version without contacting npm.',
      setup: 'Usage: tum-mcp setup [--client codex|claude|cursor|antigravity|generic] [--host local|windows]\nProvision the managed runtime and register explicitly selected clients.',
      uninstall: 'Usage: tum-mcp uninstall [--all] [--purge-runtime] [--forget-credentials]\nRemove managed client setup and this npm installation. Saved data is retained by default.\n--client NAME removes one client only. --keep-package keeps npm installed.',
    };
    console.log(help[args[0]]);
  } else {
    let packageAction = args[0] === 'update';
    if (args[0] === 'update') {
      if (args.length > 2 || (args.length === 2 && args[1] !== '--local')) throw new Error('Usage: tum-mcp update [--local]. Use --help for details.');
      if (args[1] === '--local') { packageAction = false; args = ['update']; }
    }
    if (args[0] === 'uninstall') {
      const { values } = parseArgs({ args: args.slice(1), options: {
        all: { type: 'boolean' }, client: { type: 'string' }, host: { type: 'string' },
        'keep-package': { type: 'boolean' }, 'purge-runtime': { type: 'boolean' }, 'forget-credentials': { type: 'boolean' },
      } });
      if (values.host && !['local', 'windows'].includes(values.host)) throw new Error('Choose --host local or windows.');
      if (values.client !== undefined && !['codex', 'claude', 'cursor', 'antigravity', 'generic'].includes(values.client)) throw new Error('Choose a supported --client name.');
      if (values.client && (values.all || values['purge-runtime'] || values['forget-credentials'])) throw new Error('Client-only removal cannot use --all or data/runtime cleanup options.');
      if (!values.client && !values.all) args.push('--all');
      packageAction = !values.client && !values['keep-package'];
      args = args.filter(arg => arg !== '--keep-package');
    }
    if (packageAction) {
      process.exitCode = await managePackage(args[0], args.slice(1), dataRoot());
    } else {
      let python = ['setup', 'update'].includes(args[0]) ? await ensureRuntime() : currentPython();
      if (args[0] === 'uninstall' && !python) python = await ensureRuntime();
      if (!python) throw new Error('SETUP_REQUIRED: Run tum-mcp setup first.');
      const forwarded = args;
      const env = { ...process.env, TUM_MCP_NPM_LAUNCHER: '1' }; delete env.PYTHONPATH; delete env.PYTHONHOME;
      const purge = args[0] === 'uninstall' && args.includes('--purge-runtime');
      const release = purge ? await acquireSetupLock() : null;
      try {
        const child = spawnSync(python, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
        if (child.error) throw new Error('Managed backend could not start; run setup again.');
        process.exitCode = child.status ?? (child.signal === 'SIGINT' ? 130 : 1);
        if (purge && child.status === 0) await removeRuntimeFiles();
      } finally { if (release) await release(); }
    }
  }
} catch (error) { console.error(error.message); process.exitCode = 2; }
