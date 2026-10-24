#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { acquireSetupLock, currentPython, ensureRuntime, removeRuntimeFiles } from './runtime.mjs';

const args = process.argv.slice(2);
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
try {
  if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    console.log(`TUM MCP ${version}\nCommands: setup [--client codex|claude|cursor|antigravity|generic], connect, scope, discover, status, doctor [--json] [--live], serve, skills, workspace, actions, logout, uninstall, update\nRun connect without arguments to select services and an installed Chromium browser. Run setup explicitly to provision the managed Python backend.`);
  } else if (['--version', 'version'].includes(args[0])) {
    console.log(version);
  } else if (['setup', 'update'].includes(args[0]) && args.length === 2 && ['--help', '-h'].includes(args[1])) {
    console.log(args[0] === 'update'
      ? 'Usage: tum-mcp update\nRefresh previously configured clients for the installed npm version.\nDownload a newer version first: npm install --global @jamestesting888/tum-mcp@latest'
      : 'Usage: tum-mcp setup [--client codex|claude|cursor|antigravity|generic] [--host local|windows]\nProvision the managed runtime and register explicitly selected clients.');
  } else {
    if (args[0] === 'update' && args.length !== 1) throw new Error('Usage: tum-mcp update (no arguments). Use --help for the update workflow.');
    const setup = ['setup', 'update'].includes(args[0]);
    const python = setup ? await ensureRuntime() : currentPython();
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
} catch (error) { console.error(error.message); process.exitCode = 2; }
