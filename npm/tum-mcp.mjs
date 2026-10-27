#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { acquireSetupLock, currentPython, dataRoot, ensureRuntime, removeRuntimeFiles } from './runtime.mjs';
import { managePackage } from './package-manager.mjs';
import { printHelp } from './ui.mjs';

let args = process.argv.slice(2);
const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
try {
  const wantsHelp = args.length === 0 || args.some(arg => ['--help', '-h'].includes(arg));
  const helpPython = wantsHelp ? currentPython() : null;
  if (helpPython) {
    const forwarded = args.length ? args.filter(arg => !['--local', '--keep-package'].includes(arg)) : ['--help'];
    const env = { ...process.env }; delete env.PYTHONPATH; delete env.PYTHONHOME;
    const child = spawnSync(helpPython, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
    if (child.error) throw new Error('Managed backend could not start; run setup again.');
    process.exitCode = child.status ?? 1;
  } else if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    printHelp(version, 'Campus tools and local study workflows.', 'tum-mcp [OPTIONS] COMMAND [ARGS]...', [
      ['Options', [['--version', 'Show the installed version.'], ['-h, --help', 'Show this help.']]],
      ['Commands', [
        ['setup', 'Configure your coding client and managed runtime.'],
        ['connect', 'Sign in to selected campus services.'],
        ['status', 'Show saved connections and optional workflows.'],
        ['doctor', 'Check installation and authentication.'],
        ['install', 'Choose optional Lecture, Studocu or Audio Notes workflows.'],
        ['uninstall', 'Choose extensions or All to remove TUM MCP.'],
        ['manage', 'Manage TUMonline permissions.'],
        ['skills', 'Inspect and validate workflow skills.'],
        ['study', 'Prepare, preview and publish a course app.'],
        ['lecture', 'Prepare lecture recording evidence (optional extension).'],
        ['studocu', 'Collect selected supplementary materials (optional extension).'],
        ['discover', 'List accessible courses or channels.'],
        ['update', 'Update the package and configured clients.'],
        ['logout', 'Remove one saved connection.'],
        ['serve', 'Run the MCP server over stdio.'],
        ['version', 'Show the installed version.'],
      ]],
      ['Get started', [['tum-mcp setup --client codex', 'Prepare the backend and a client.'], ['tum-mcp connect', 'Choose services and sign in.']]],
    ]);
  } else if (['--version', 'version'].includes(args[0])) {
    console.log(version);
  } else if (args[0] === 'install' && args.some(arg => ['--help', '-h'].includes(arg))) {
    printHelp(version, 'Choose optional workflows to install, or provide their names.', 'tum-mcp install [lecture|studocu|audio-notes]... [OPTIONS]', [
      ['Options', [['--asr / --no-asr', 'Provision isolated lecture recognition; models load on demand.'], ['--json', 'Print machine-readable results.'], ['-h, --help', 'Show this help.']]],
    ]);
  } else if (['setup', 'update', 'uninstall'].includes(args[0]) && args.some(arg => ['--help', '-h'].includes(arg))) {
    const help = {
      update: {
        description: 'Install the latest npm release and refresh configured clients.',
        usage: 'tum-mcp update [OPTIONS]',
        options: [['--local', 'Refresh the installed version without contacting npm.']],
      },
      setup: {
        description: 'Prepare the runtime and choose coding clients to configure.',
        usage: 'tum-mcp setup [OPTIONS]',
        options: [['--client NAME', 'Choose codex, claude, cursor, antigravity or generic; repeat as needed.'], ['--host local|windows', 'Choose the client host; windows is for WSL registrations.']],
      },
      uninstall: {
        description: 'Remove managed setup while retaining saved user data by default.',
        usage: 'tum-mcp uninstall [lecture|studocu|audio-notes]... [OPTIONS]',
        options: [['(no arguments)', 'Choose extensions or All in the interactive picker.'], ['--client NAME', 'Remove one client registration.'], ['--host local|windows', 'Choose the client host.'], ['--purge-runtime', 'Remove verified runtimes when All is selected.'], ['--forget-credentials', 'Forget saved credentials when All is selected.']],
      },
    };
    const selected = help[args[0]];
    printHelp(version, selected.description, selected.usage, [
      ['Options', [...selected.options, ['-h, --help', 'Show this help.']]],
    ]);
  } else {
    const hasExtension = args.slice(1).some(arg => ['lecture', 'studocu', 'audio-notes'].includes(arg));
    let packageAction = args[0] === 'update';
    if (args[0] === 'update') {
      if (args.length > 2 || (args.length === 2 && args[1] !== '--local')) throw new Error('Usage: tum-mcp update [--local]. Use --help for details.');
      if (args[1] === '--local') { packageAction = false; args = ['update']; }
    }
    if (args[0] === 'uninstall' && !hasExtension) {
      const { values } = parseArgs({ args: args.slice(1), options: {
        all: { type: 'boolean' }, client: { type: 'string' }, host: { type: 'string' },
        'keep-package': { type: 'boolean' }, 'purge-runtime': { type: 'boolean' }, 'forget-credentials': { type: 'boolean' }, json: { type: 'boolean' },
      } });
      if (values.host && !['local', 'windows'].includes(values.host)) throw new Error('Choose --host local or windows.');
      if (values.client !== undefined && !['codex', 'claude', 'cursor', 'antigravity', 'generic'].includes(values.client)) throw new Error('Choose a supported --client name.');
      if (values.client && (values.all || values['purge-runtime'] || values['forget-credentials'])) throw new Error('Client-only removal cannot use --all or data/runtime cleanup options.');
      if (values.all && values.json) throw new Error('--json requires named extensions.');
      if (values['keep-package'] && !values.all && !values.client) throw new Error('Use --client for registration-only removal.');
      packageAction = Boolean(values.all) && !values['keep-package'];
      args = args.filter(arg => arg !== '--keep-package');
    }
    if (packageAction) {
      process.exitCode = await managePackage(args[0], args.slice(1), dataRoot());
    } else {
      let python = ['setup', 'update', 'install'].includes(args[0]) ? await ensureRuntime() : currentPython();
      if (args[0] === 'uninstall' && !python) python = await ensureRuntime();
      if (!python) throw new Error('SETUP_REQUIRED: Run tum-mcp setup first.');
      const forwarded = args;
      const env = { ...process.env, TUM_MCP_NPM_LAUNCHER: '1' }; delete env.PYTHONPATH; delete env.PYTHONHOME;
      const purge = args[0] === 'uninstall' && args.includes('--purge-runtime') && args.includes('--all');
      const release = purge ? await acquireSetupLock() : null;
      try {
        const child = spawnSync(python, ['-I', '-m', 'tum_mcp', ...forwarded], { env, stdio: 'inherit', shell: false });
        if (child.error) throw new Error('Managed backend could not start; run setup again.');
        process.exitCode = child.status ?? (child.signal === 'SIGINT' ? 130 : 1);
        if (args[0] === 'uninstall' && child.status === 20) {
          process.exitCode = await managePackage('uninstall', [...args.slice(1), '--all'], dataRoot());
        }
        if (purge && child.status === 0) await removeRuntimeFiles();
      } finally { if (release) await release(); }
    }
  }
} catch (error) { console.error(error.message); process.exitCode = 2; }
