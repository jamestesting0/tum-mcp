#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { acquireSetupLock, currentPython, dataRoot, ensureRuntime, removeRuntimeFiles } from './runtime.mjs';
import { managePackage } from './package-manager.mjs';
import { hasHelp, printHelp } from './ui.mjs';

let args = process.argv.slice(2);
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
try {
  const wantsHelp = args.length === 0 || args.some(arg => ['--help', '-h'].includes(arg));
  const helpPython = wantsHelp ? currentPython() : null;
  if (helpPython) {
    const forwarded = args.length ? args.filter(arg => !['--local', '--keep-package'].includes(arg)) : ['--help'];
    const env = { ...process.env }; delete env.PYTHONPATH; delete env.PYTHONHOME;
    const child = spawnSync(helpPython, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
    if (child.error) throw new Error('The TUM MCP runtime could not start; run tum-mcp setup to repair it.');
    process.exitCode = child.status ?? 1;
  } else if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    printHelp(version);
  } else if (['--version', 'version'].includes(args[0])) {
    console.log(version);
  } else if (hasHelp(args[0]) && args.some(arg => ['--help', '-h'].includes(arg))) {
    printHelp(version, args[0]);
  } else {
    const hasExtension = args.slice(1).some(arg => ['lecture', 'audio-notes', 'video-notes', 'course-memory'].includes(arg));
    let packageAction = args[0] === 'update';
    if (args[0] === 'update') {
      if (args.length > 2 || (args.length === 2 && args[1] !== '--local')) throw new Error('Usage: tum-mcp update [--local]. Run tum-mcp update --help for details.');
      if (args[1] === '--local') { packageAction = false; args = ['update']; }
    }
    if (args[0] === 'uninstall' && !hasExtension) {
      const { values } = parseArgs({ args: args.slice(1), options: {
        all: { type: 'boolean' }, client: { type: 'string' }, host: { type: 'string' },
        'keep-package': { type: 'boolean' }, 'purge-runtime': { type: 'boolean' }, 'forget-credentials': { type: 'boolean' }, json: { type: 'boolean' },
      } });
      if (values.host && !['local', 'windows'].includes(values.host)) throw new Error('--host must be local or windows.');
      if (values.client !== undefined && !['codex', 'claude', 'cursor', 'antigravity', 'generic'].includes(values.client)) throw new Error('--client must be codex, claude, cursor, antigravity or generic.');
      if (values.client && (values.all || values['purge-runtime'] || values['forget-credentials'])) throw new Error('--client removes one registration; it cannot be combined with --all, --purge-runtime or --forget-credentials.');
      if (values.all && values.json) throw new Error('--json works only with named workflows, e.g. tum-mcp uninstall lecture --json.');
      if (values['keep-package'] && !values.all && !values.client) throw new Error('--keep-package needs --all or --client NAME.');
      packageAction = Boolean(values.all) && !values['keep-package'];
      args = args.filter(arg => arg !== '--keep-package');
    }
    if (packageAction) {
      process.exitCode = await managePackage(args[0], args.slice(1), dataRoot());
    } else {
      let python = ['setup', 'update', 'install'].includes(args[0]) ? await ensureRuntime() : currentPython();
      if (args[0] === 'uninstall' && !python) python = await ensureRuntime();
      if (!python) throw new Error('TUM MCP is not set up yet. Run tum-mcp setup first.');
      const forwarded = args;
      const env = { ...process.env, TUM_MCP_NPM_LAUNCHER: '1' }; delete env.PYTHONPATH; delete env.PYTHONHOME;
      const purge = args[0] === 'uninstall' && args.includes('--purge-runtime') && args.includes('--all');
      const release = purge ? await acquireSetupLock() : null;
      try {
        const child = spawnSync(python, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
        if (child.error) throw new Error('The TUM MCP runtime could not start; run tum-mcp setup to repair it.');
        process.exitCode = child.status ?? (child.signal === 'SIGINT' ? 130 : 1);
        if (args[0] === 'uninstall' && child.status === 20) {
          process.exitCode = await managePackage('uninstall', [...args.slice(1), '--all'], dataRoot());
        }
        if (purge && child.status === 0) await removeRuntimeFiles();
      } finally { if (release) await release(); }
    }
  }
} catch (error) { console.error(`Error: ${error.message}`); process.exitCode = 2; }
