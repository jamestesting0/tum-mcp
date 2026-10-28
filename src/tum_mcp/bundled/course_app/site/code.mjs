import { node, append } from './dom.mjs';

// Syntax highlighting without a library: a small scanner per language family builds DOM
// spans (never HTML strings), so code from course material cannot inject markup.
const words = text => new Set(text.split(' '));
const C_LITERALS = 'true false null';
const JAVA = 'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public record return sealed permits short static strictfp super switch synchronized this throw throws transient try var void volatile while yield';
const C = 'auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while';
const CPP = `${C} bool catch class constexpr delete explicit friend namespace new noexcept nullptr operator override private protected public template this throw try typename using virtual`;
const JS = 'async await break case catch class const continue debugger default delete do else export extends finally for from function if import in instanceof let new of return static super switch this throw try typeof var void while with yield';
const TS = `${JS} abstract any as boolean declare enum implements interface keyof namespace never number private protected public readonly string type unknown`;
const families = {
  java: { keywords: words(JAVA), literals: words(C_LITERALS), text: true },
  kotlin: { keywords: words('as break by catch class companion constructor continue data do else enum for fun if import in init interface internal is lateinit object open override package private protected public return sealed super suspend this throw try typealias val var when while'), literals: words(C_LITERALS), text: true },
  scala: { keywords: words('abstract case catch class def do else extends final finally for if implicit import lazy match new object override package private protected return sealed super this throw trait try type val var while with yield'), literals: words(C_LITERALS), text: true },
  c: { keywords: words(C), literals: words('NULL true false'), hash: true },
  cpp: { keywords: words(CPP), literals: words('true false nullptr NULL'), hash: true },
  csharp: { keywords: words('abstract as base bool break case catch char class const continue decimal default delegate do double else enum event explicit extern finally fixed float for foreach if implicit in int interface internal is lock long namespace new object operator out override params private protected public readonly ref return sealed short static string struct switch this throw try typeof uint using var virtual void while'), literals: words(C_LITERALS) },
  javascript: { keywords: words(JS), literals: words('true false null undefined NaN'), templates: true },
  typescript: { keywords: words(TS), literals: words('true false null undefined NaN'), templates: true },
  go: { keywords: words('break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var'), literals: words('true false nil iota'), templates: true },
  rust: { keywords: words('as async await break const continue crate dyn else enum extern fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait type unsafe use where while'), literals: words('true false None Some Ok Err') },
  swift: { keywords: words('as break case catch class continue default defer do else enum extension fallthrough for func guard if import in init inout internal is let private protected public repeat return self static struct subscript super switch throw throws try var where while'), literals: words('true false nil') },
  python: { keywords: words('and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'), literals: words('True False None'), hashComments: true, triple: true, decorators: true },
  shell: { keywords: words('if then else elif fi for while until do done case esac function in return local export echo exit'), literals: words('true false'), hashComments: true, variables: true },
  sql: { keywords: words('select from where and or not insert into values update set delete create table drop alter add primary key foreign references join left right inner outer on group by order having limit offset as distinct union all null is in exists between like count sum avg min max'), literals: words('true false null'), dashComments: true, caseless: true },
  json: { keywords: new Set(), literals: words('true false null'), noComments: true },
};
const aliases = { java: 'java', kotlin: 'kotlin', kt: 'kotlin', scala: 'scala', c: 'c', h: 'c', cpp: 'cpp', 'c++': 'cpp', cc: 'cpp', hpp: 'cpp', csharp: 'csharp', cs: 'csharp', 'c#': 'csharp', javascript: 'javascript', js: 'javascript', mjs: 'javascript', jsx: 'javascript', typescript: 'typescript', ts: 'typescript', tsx: 'typescript', go: 'go', rust: 'rust', rs: 'rust', swift: 'swift', python: 'python', py: 'python', bash: 'shell', sh: 'shell', shell: 'shell', zsh: 'shell', sql: 'sql', json: 'json', gradle: 'java', groovy: 'java' };
const names = { java: 'Java', kotlin: 'Kotlin', scala: 'Scala', c: 'C', cpp: 'C++', csharp: 'C#', javascript: 'JavaScript', typescript: 'TypeScript', go: 'Go', rust: 'Rust', swift: 'Swift', python: 'Python', shell: 'Shell', sql: 'SQL', json: 'JSON' };

function languageOf(language, path = '') {
  const key = ((language || '').toLowerCase().match(/^[a-z0-9#+]+/) || [path.split('.').pop() || ''])[0].toLowerCase();
  return aliases[key] || null;
}
export function languageName(language, path = '') {
  const family = languageOf(language, path);
  return family ? names[family] : (language || '');
}

// Tokens are [type, text] pairs; type '' is plain text.
function tokenize(code, family) {
  const spec = families[family], tokens = [];
  if (!spec) return [['', code]];
  const push = (type, text) => { const last = tokens.at(-1); if (last && last[0] === type) last[1] += text; else tokens.push([type, text]); };
  let i = 0, lineStart = true;
  const until = (end, from) => { const at = code.indexOf(end, from); return at < 0 ? code.length : at + end.length; };
  while (i < code.length) {
    const rest = code.slice(i, i + 3), ch = code[i];
    let end = 0, type = '';
    if (!spec.noComments && !spec.hashComments && !spec.dashComments && rest.startsWith('//')) { end = until('\n', i) - (code.indexOf('\n', i) < 0 ? 0 : 1); type = 'comment'; }
    else if (!spec.noComments && !spec.hashComments && !spec.dashComments && rest.startsWith('/*')) { end = until('*/', i + 2); type = 'comment'; }
    else if ((spec.hashComments && ch === '#') || (spec.dashComments && rest.startsWith('--'))) { const at = code.indexOf('\n', i); end = at < 0 ? code.length : at; type = 'comment'; }
    else if (spec.hash && ch === '#' && lineStart) { const at = code.indexOf('\n', i); end = at < 0 ? code.length : at; type = 'meta'; }
    else if ((spec.triple || spec.text) && (rest === '"""' || (spec.triple && rest === "'''"))) { end = until(rest, i + 3); type = 'string'; }
    else if (ch === '"' || ch === "'" || (spec.templates && ch === '`')) {
      let at = i + 1;
      while (at < code.length && code[at] !== ch && (ch === '`' || code[at] !== '\n')) at += code[at] === '\\' ? 2 : 1;
      end = Math.min(code.length, at + 1); type = 'string';
    } else if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(code[i + 1] || ''))) {
      end = i + /^(0[xb][0-9a-f_]+|[0-9][0-9_]*(\.[0-9_]+)?(e[+-]?[0-9]+)?|\.[0-9]+)[a-z]*/i.exec(code.slice(i))[0].length; type = 'number';
    } else if (ch === '@' && (spec.decorators || spec.text || families[family] === families.java) && /[A-Za-z_]/.test(code[i + 1] || '')) {
      end = i + 1 + /^[A-Za-z_][\w.]*/.exec(code.slice(i + 1))[0].length; type = 'meta';
    } else if (spec.variables && ch === '$' && /[{\w]/.test(code[i + 1] || '')) {
      end = i + 1 + /^(\{[^}]*\}|\w+)/.exec(code.slice(i + 1))[0].length; type = 'variable';
    } else if (/[A-Za-z_$]/.test(ch)) {
      const word = /^[A-Za-z_$][\w$]*/.exec(code.slice(i))[0], key = spec.caseless ? word.toLowerCase() : word;
      end = i + word.length;
      type = spec.keywords.has(key) ? 'keyword' : spec.literals.has(key) ? 'literal'
        : /^\s*\(/.test(code.slice(end, end + 40)) ? 'function' : /^[A-Z][a-z0-9]/.test(word) && family !== 'sql' ? 'type' : '';
    } else { end = i + 1; }
    const text = code.slice(i, end);
    push(type, text);
    lineStart = text.includes('\n') ? /\n[ \t]*$/.test(text) : lineStart && /^[ \t]*$/.test(text);
    i = end;
  }
  return tokens;
}

// Split tokens into lines so every line can carry its number and a mark.
function lines(code, language) {
  const result = [[]];
  for (const [type, text] of tokenize(code, languageOf(language))) {
    text.split('\n').forEach((part, index) => {
      if (index) result.push([]);
      if (part) result.at(-1).push([type, part]);
    });
  }
  return result;
}
function lineNode(parts, number, marked) {
  const line = node('span', `code-line${marked ? ' marked' : ''}`);
  if (number) line.dataset.line = String(number);
  for (const [type, text] of parts) line.append(type ? node('span', `tok-${type}`, text) : document.createTextNode(text));
  return line;
}

// A highlighted listing; `start` numbers an excerpt from its real line, `marked` lines stand out.
export function renderCode(code, language, { numbers = false, start = 1, marked = new Set() } = {}) {
  const listing = node('code', `code-view${numbers ? ' numbered' : ''}`);
  lines(code, language).forEach((parts, index) => {
    if (index) listing.append('\n');
    listing.append(lineNode(parts, numbers ? start + index : 0, marked.has(start + index)));
  });
  return append(node('pre', 'code-pre'), listing);
}
// "12" or "12-18" as a set of line numbers.
export function lineSet(lines) {
  if (!lines) return new Set();
  const [first, last = first] = String(lines).split('-').map(Number);
  return new Set(Array.from({ length: last - first + 1 }, (_, index) => first + index));
}
export function markLines(pre, marked) {
  for (const line of pre.querySelectorAll('.code-line')) line.classList.toggle('marked', marked.has(Number(line.dataset.line)));
}

// A textarea over its own highlighted copy: Tab indents, Enter keeps the indentation, and
// Esc then Tab leaves the editor, so keyboard users are never trapped.
export function codeEditor(input, language, marked = new Set()) {
  const shell = node('div', 'code-editor'), gutter = node('pre', 'code-editor-gutter'), view = node('pre', 'code-editor-view');
  gutter.setAttribute('aria-hidden', 'true'); view.setAttribute('aria-hidden', 'true');
  input.classList.add('code-editor-input'); input.spellcheck = false; input.autocapitalize = 'off'; input.setAttribute('autocorrect', 'off');
  input.wrap = 'off';
  const paint = () => {
    const rows = lines(input.value, language);
    view.replaceChildren(); rows.forEach((parts, index) => { if (index) view.append('\n'); view.append(lineNode(parts, 0, marked.has(index + 1))); });
    view.append('\n');
    gutter.textContent = rows.map((_, index) => index + 1).join('\n');
    input.rows = Math.max(8, rows.length + 1);
  };
  let leaving = false;
  const insert = text => {
    if (document.execCommand('insertText', false, text)) return;
    input.setRangeText(text, input.selectionStart, input.selectionEnd, 'end'); input.dispatchEvent(new Event('input'));
  };
  input.addEventListener('keydown', event => {
    const plain = !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey;
    if (event.key === 'Tab' && plain && !leaving) { event.preventDefault(); insert('    '); }
    else if (event.key === 'Enter' && plain && !event.isComposing) {
      const before = input.value.slice(0, input.selectionStart), line = before.slice(before.lastIndexOf('\n') + 1);
      event.preventDefault(); insert(`\n${line.match(/^[ \t]*/)[0]}${/[{:([]\s*$/.test(line) ? '    ' : ''}`);
    }
    leaving = event.key === 'Escape';
  });
  input.addEventListener('blur', () => { leaving = false; });
  // Marks show where a step pointed; they clear once the student starts typing.
  input.addEventListener('input', () => { marked = new Set(); paint(); });
  input.addEventListener('scroll', () => { view.scrollLeft = input.scrollLeft; view.scrollTop = input.scrollTop; });
  const stack = append(node('div', 'code-editor-stack'), view, input);
  shell.append(gutter, stack); paint();
  return shell;
}
