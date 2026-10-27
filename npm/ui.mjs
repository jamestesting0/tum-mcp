// Bootstrap help stays available before Python setup; installed help uses the backend.
const color = process.stdout.isTTY && !('NO_COLOR' in process.env) && process.env.TERM !== 'dumb';
const width = Math.min(Number(process.env.COLUMNS) || process.stdout.columns || 80, 100);
const styled = (text, code) => color ? `\x1b[${code}m${text}\x1b[0m` : text;

function line(text, indent = '') {
  const available = Math.max(16, width - indent.length);
  let remaining = text;
  while (remaining.length > available) {
    const space = remaining.lastIndexOf(' ', available);
    const end = space > 0 ? space : available;
    console.log(indent + remaining.slice(0, end));
    remaining = remaining.slice(end).trimStart();
  }
  console.log(indent + remaining);
}

export function printHelp(version, description, usage, sections = []) {
  console.log(`${styled('TUM MCP', '1')}  Help  ${styled(version, '2')}`);
  line(description);
  console.log();
  line('Usage');
  line(usage, '  ');
  console.log();
  for (const [title, rows] of sections) {
    console.log(styled(title, '1'));
    const labelWidth = Math.max(...rows.map(([label]) => label.length)) + 2;
    for (const [label, detail] of rows) {
      if (width < 70 || labelWidth > width / 2) {
        line(label);
        line(detail, '  ');
      } else {
        const prefix = label.padEnd(labelWidth);
        const available = Math.max(16, width - prefix.length);
        const words = detail.split(' ');
        let row = '';
        let first = true;
        for (const word of words) {
          if (row && row.length + word.length + 1 > available) {
            console.log((first ? prefix : ' '.repeat(labelWidth)) + row);
            first = false;
            row = '';
          }
          row += (row ? ' ' : '') + word;
        }
        console.log((first ? prefix : ' '.repeat(labelWidth)) + row);
      }
    }
    console.log();
  }
}
