#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { currentPython, ensureRuntime } from './runtime.mjs';

const args = process.argv.slice(2);
try {
  if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    console.log('TUM MCP 0.5.0\nCommands: setup [--client codex|claude|cursor|antigravity|generic], connect, scope, discover, status, doctor [--json] [--live], serve, skills, workspace, actions, logout, uninstall, update\nRun connect without arguments to select services and an installed Chromium browser. Run setup explicitly to provision the managed Python backend.');
  } else if (['--version', 'version'].includes(args[0])) {
    console.log('0.5.0');
  } else {
    const setup = ['setup', 'update'].includes(args[0]);
    const python = setup ? await ensureRuntime() : currentPython();
    if (!python) throw new Error('SETUP_REQUIRED: Run tum-mcp setup first.');
    const forwarded = args[0] === 'update' ? ['status'] : args;
    const env = { ...process.env }; delete env.PYTHONPATH; delete env.PYTHONHOME;
    const child = spawnSync(python, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
    if (child.error) throw new Error('Managed backend could not start; run setup again.');
    process.exitCode = child.status ?? 1;
  }
} catch (error) { console.error(error.message); process.exitCode = 2; }
