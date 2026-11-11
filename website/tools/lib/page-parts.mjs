const escape = text => String(text).replace(/[&<>"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[character]);

const VARS = {
  '--wb-title': 'titleBar.activeBackground', '--wb-title-fg': 'titleBar.activeForeground',
  '--wb-act': 'activityBar.background', '--wb-act-fg': 'activityBar.foreground', '--wb-act-muted': 'activityBar.inactiveForeground',
  '--wb-side': 'sideBar.background', '--wb-side-fg': 'sideBar.foreground', '--wb-border': ['sideBar.border', 'panel.border'],
  '--wb-editor': 'editor.background', '--wb-fg': 'editor.foreground',
  '--wb-tabs': 'editorGroupHeader.tabsBackground', '--wb-tab-active': 'tab.activeBackground', '--wb-tab-fg': 'tab.activeForeground', '--wb-tab-top': 'tab.activeBorderTop',
  '--wb-panel': 'panel.background', '--wb-status': 'statusBar.background', '--wb-status-fg': 'statusBar.foreground',
  '--wb-accent': ['button.background', 'activityBarBadge.background'], '--wb-button': ['button.background', 'activityBarBadge.background'], '--wb-button-fg': 'button.foreground',
  '--wb-input': 'input.background', '--wb-input-border': ['input.border', 'panel.border'],
  '--wb-select': ['list.inactiveSelectionBackground', 'list.activeSelectionBackground'], '--wb-hover': 'list.hoverBackground',
  '--wb-line-number': 'editorLineNumber.foreground', '--wb-muted': ['descriptionForeground', 'tab.inactiveForeground'],
};

// VS Code's own defaults for anything a theme leaves unset (terminalColorRegistry, git decorations).
const DEFAULTS = {
  dark: { '--wb-act-muted': '#868686', '--wb-button-fg': '#ffffff', '--wb-added': '#81b88b', '--wb-tok-key': '#9cdcfe', '--wb-tok-string': '#ce9178', '--wb-tok-number': '#b5cea8', '--wb-tok-heading': '#569cd6',
    '--term-dim': '#8b8b8b', '--term-cyan': '#11a8cd', '--term-green': '#0dbc79', '--term-blue': '#2472c8', '--term-yellow': '#e5e510', '--term-red': '#cd3131' },
  light: { '--wb-act-muted': '#616161', '--wb-button-fg': '#ffffff', '--wb-added': '#587c0c', '--wb-tok-key': '#0451a5', '--wb-tok-string': '#a31515', '--wb-tok-number': '#098658', '--wb-tok-heading': '#800000',
    '--term-dim': '#6e6e6e', '--term-cyan': '#0598bc', '--term-green': '#00bc00', '--term-blue': '#0451a5', '--term-yellow': '#949800', '--term-red': '#cd3131' },
};

export function paletteCss(references) {
  const blocks = [];
  for (const [host, prefix] of [['codex', 'vscode'], ['cursor', 'cursor']]) {
    for (const mode of ['light', 'dark']) {
      const theme = references.themes[`${prefix}-${mode}`];
      const values = { ...DEFAULTS[mode] };
      for (const [variable, keys] of Object.entries(VARS)) {
        const key = [keys].flat().find(name => theme[name]);
        if (key) values[variable] = theme[key];
      }
      blocks.push(`:root[data-theme="${mode}"] .wb-${host} { ${Object.entries(values).map(([name, value]) => `${name}: ${value};`).join(' ')} }`);
    }
  }
  return blocks.join('\n');
}

export function hostTabs(story) {
  return story.hosts.map((host, index) =>
    `<button class="host-tab" type="button" role="tab" data-host-tab="${host.key}" aria-selected="${index === 0}" tabindex="${index === 0 ? 0 : -1}"><span data-mark></span><span>${escape(host.label)}</span></button>`).join('');
}

export function chapterParts(story) {
  return {
    anchors: story.chapters.map(chapter => `<div class="chapter-anchor" id="${chapter.key}"></div>`).join(''),
    // Playback bar segments; main.js sizes each by its chapter's play time.
    links: story.chapters.map(chapter => `<span class="seg" data-chapter="${chapter.key}"><span class="seg-rail"><span class="seg-fill"></span></span><span class="seg-label">${escape(chapter.label)}</span></span>`).join(''),
  };
}

export function commandList(story) {
  return story.commands.map(command =>
    `<li class="command"><code>${escape(command)}</code><button class="copy" type="button" aria-label="Copy command" data-copy="${escape(command)}"><span class="copy-icon" data-copy-label aria-hidden="true"></span></button></li>`).join('');
}

export const credits = ['Editor icons: Codicons by Microsoft, CC BY 4.0', 'Type: Atkinson Hyperlegible Next, SIL Open Font License']
  .map(line => `<li>${line}</li>`).join('');
