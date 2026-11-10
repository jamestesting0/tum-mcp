// Bootstrap help stays available before Python setup; help.json is exported from the Python CLI.
import { readFileSync } from 'node:fs';

const help = JSON.parse(readFileSync(new URL('./help.json', import.meta.url), 'utf8'));
const color = process.stdout.isTTY && !('NO_COLOR' in process.env) && process.env.TERM !== 'dumb';
const width = Math.min(Number(process.env.COLUMNS) || process.stdout.columns || 80, 100);
const styled = (text, code) => color ? `\x1b[${code}m${text}\x1b[0m` : text;

function wrap(text, available) {
  const lines = [];
  let row = '';
  for (const word of text.split(' ')) {
    if (row && row.length + word.length + 1 > available) { lines.push(row); row = ''; }
    row += (row ? ' ' : '') + word;
  }
  lines.push(row);
  return lines;
}

function rows(entries) {
  const labelWidth = Math.max(...entries.map(([label]) => label.length)) + 2;
  for (const [label, detail] of entries) {
    if (width < 70 || labelWidth > width / 2) {
      for (const line of wrap(label, width)) console.log(styled(line, '1'));
      for (const line of wrap(detail, width - 2)) console.log('  ' + line);
    } else {
      wrap(detail, width - labelWidth).forEach((line, index) => {
        console.log((index ? ' '.repeat(labelWidth) : label.padEnd(labelWidth)) + line);
      });
    }
  }
  console.log();
}

function section(title, entries) {
  if (!entries.length) return;
  console.log(styled(title, '1'));
  rows(entries);
}

export function hasHelp(command) { return Object.hasOwn(help.commands, command); }

export function printHelp(version, command) {
  const selected = command ? help.commands[command] : help;
  console.log(`${styled('TUM MCP', '1')}  ${command ? `tum-mcp ${command}` : styled(version, '2')}`);
  for (const line of wrap(selected.description, width)) console.log(styled(line, '2'));
  console.log();
  rows([['Usage', selected.usage]]);
  section('Arguments', selected.arguments || []);
  section('Options', selected.options);
  for (const [title, entries] of Object.entries(command ? {} : help.groups)) section(title, entries);
}
