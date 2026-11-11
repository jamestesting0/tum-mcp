// The parts of a step that play by themselves once the tour reaches it: the CLI in the terminal,
// the agent in the chat, the sign-in window and the app opening. Times are in milliseconds and
// fixed, so the pace is the same however fast the visitor scrolls.

export const PACE = {
  typeChar: 46,
  typeMin: 560,
  typeMax: 1500,
  afterTyping: 320,
  lines: 650,
  frame: 1100,
  sequence: 640,
  composeChar: 34,
  composeMin: 760,
  composeMax: 1800,
  send: 220,
  toolRow: 720,
  answer: 1000,
  chatHold: 650,
  appOpen: 520,
};

const typing = text => Math.min(PACE.typeMax, Math.max(PACE.typeMin, text.length * PACE.typeChar));
const plans = new WeakMap();

// A terminal's blocks become timed events. Recorded screens replace the screen before them,
// as a full-screen program redraws; `exits` marks where the command returns to the prompt.
export function terminalPlan(blocks, frames) {
  if (plans.has(blocks)) return plans.get(blocks);
  const events = [];
  let at = 0;
  for (const block of blocks) {
    if (block.command != null) {
      const duration = block.type ? typing(block.command) : 0;
      events.push({ kind: 'command', block, at, duration });
      at += duration + (block.type ? PACE.afterTyping : 0);
    } else if (block.lines) {
      events.push({ kind: 'lines', block, at });
      at += block.hold ?? PACE.lines;
    } else if (block.frame) {
      events.push({ kind: 'screen', screen: frames[block.frame], exits: block.exits, at });
      at += block.hold ?? PACE.frame;
    } else if (block.sequence) {
      for (const screen of frames[block.sequence]) {
        events.push({ kind: 'screen', screen, at });
        at += block.every ?? PACE.sequence;
      }
      at += (block.hold ?? PACE.frame) - (block.every ?? PACE.sequence);
    } else if (block.browser) {
      events.push({ kind: 'browser', at, duration: block.browser });
      at += block.browser;
    }
  }
  const plan = { events, duration: at };
  plans.set(blocks, plan);
  return plan;
}

// When each chat message appears: the sent prompt first, then tool rows, then the answer.
function chatPlan(step) {
  const chat = step.chat ?? {};
  if (chat.compose) {
    const compose = Math.min(PACE.composeMax, Math.max(PACE.composeMin, chat.compose.length * PACE.composeChar));
    return { times: [], compose, duration: compose + PACE.chatHold };
  }
  const times = [];
  let at = 0;
  if (chat.send) { times.push(at); at += PACE.send; }
  for (const message of chat.messages ?? []) {
    at += message.role === 'agent' ? PACE.answer : PACE.toolRow;
    times.push(at);
  }
  return { times, compose: 0, duration: times.length ? at + PACE.chatHold : 0 };
}

export function stepPlan(step, frames) {
  const terminal = step.terminal ? terminalPlan(step.terminal.blocks, frames) : null;
  const chat = chatPlan(step);
  const browser = terminal?.events.find(event => event.kind === 'browser') ?? null;
  const played = Math.max(terminal?.duration ?? 0, chat.duration);
  // The app opens after what plays before it; a step that only shows the app has nothing to wait for.
  const appAt = step.app && played ? played : 0;
  return { terminal, chat, browser, appAt, duration: appAt ? appAt + PACE.appOpen : played };
}

export function chatAt(step, plan, ms) {
  const sent = step.chat?.send ? 1 : 0;
  const shown = plan.chat.times.filter(at => ms >= at).length;
  const added = step.added.chat;
  const chatCount = step.state.chat.length - added + Math.min(added, shown);
  const progress = added ? Math.max(0, shown - sent) / Math.max(1, added - sent) : 1;
  const filesAdded = step.added.files;
  const filesCount = step.state.files.length - filesAdded + Math.round(Math.min(1, progress) * filesAdded);
  const composeFraction = plan.chat.compose ? Math.min(1, ms / plan.chat.compose) : 1;
  return { chatCount, filesCount, composeFraction };
}
