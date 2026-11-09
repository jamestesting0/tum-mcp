import data from '../../data.mjs';
import { node, studyText, append, button, topicRow } from '../shell/dom.mjs';
import { iconGlyph, nextStep } from '../shell/navigation.mjs';

// Audio notes are a local-preview feature, like videos: hosted sites never ask for the index.
let tracks = [];
export async function loadAudio() {
  if (data.hosted) return tracks;
  try {
    const response = await fetch('audio/index.json', { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    const value = response.ok ? await response.json() : null;
    if (Array.isArray(value?.tracks)) tracks = value.tracks;
  } catch { /* opened without the local preview */ }
  return tracks;
}
export const hasAudio = () => tracks.length > 0;

const shelves = [['study', 'Lectures'], ['exam', 'Exam']];
const shelfName = track => (track.kind === 'study' ? 'Lecture' : 'Exam');
const trackLink = track => `#audio/${encodeURIComponent(track.stem)}`;
const shelfOf = track => tracks.filter(item => item.kind === track.kind);
function clock(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}
const minutes = seconds => `${Math.max(1, Math.round(seconds / 60))} min`;
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

// Where each track stopped and which version was heard, per course; speed is shared with videos.
const stateKey = `course-app:${data.course.identity}:audio:v1`, prefsKey = 'study-space:player';
function readJson(key) { try { const value = JSON.parse(localStorage.getItem(key)); return value && typeof value === 'object' ? value : {}; } catch { return {}; } }
const state = readJson(stateKey);
state.tracks = state.tracks && typeof state.tracks === 'object' ? state.tracks : {};
function saveState() { try { localStorage.setItem(stateKey, JSON.stringify(state)); } catch { /* lasts for this page */ } }
function heard(track) { const entry = state.tracks[track.stem]; return entry && entry.revision === track.revision ? entry : null; }
function updated(track) { const entry = state.tracks[track.stem]; return Boolean(entry && entry.revision !== track.revision); }

const rates = [1, 1.25, 1.5, 1.75, 2, 0.75];
const player = new Audio(); player.preload = 'metadata';
let current = null, frame = 0, savedAt = 0, dock = null, view = null;

function chapterIndex(track, time) {
  let index = 0;
  while (index + 1 < track.chapters.length && time >= track.chapters[index + 1].start) index++;
  return index;
}
function position(track) { return track === current ? player.currentTime : heard(track)?.time || 0; }
function remember(done = false) {
  // Until a newly chosen track has loaded, its position is not yet the student's.
  if (!current || !player.readyState) return;
  state.tracks[current.stem] = { time: done ? 0 : Math.floor(player.currentTime), revision: current.revision, done: done || Boolean(heard(current)?.done && !player.currentTime) };
  state.last = current.stem; saveState(); savedAt = Date.now();
}
function load(track) {
  if (track === current) return;
  if (current) remember();
  current = track; state.last = track.stem; state.closed = false; saveState();
  player.src = track.track;
  const entry = heard(track), rate = readJson(prefsKey).rate;
  player.defaultPlaybackRate = player.playbackRate = rates.includes(rate) ? rate : 1;
  // Resume a few seconds back, so the sentence the student stopped in starts again.
  if (entry && !entry.done && entry.time > 5) player.addEventListener('loadedmetadata', () => { player.currentTime = entry.time - 3; paint(); }, { once: true });
  session(); paint();
}
function play(track, at) {
  load(track);
  if (at !== undefined) {
    if (player.readyState) player.currentTime = at;
    else player.addEventListener('loadedmetadata', () => { player.currentTime = at; }, { once: true });
  }
  player.play().catch(() => {});
}
const toggle = track => (track === current && !player.paused ? player.pause() : play(track));
function seek(seconds) { if (!current) return; player.currentTime = Math.max(0, Math.min(current.duration, seconds)); paint(); }
function chapterJump(step) {
  if (!current) return;
  const index = chapterIndex(current, player.currentTime);
  // Back from inside a chapter restarts it; from its first seconds, it goes to the one before.
  const target = step < 0 && player.currentTime - current.chapters[index].start > 3 ? index : index + step;
  seek(current.chapters[Math.max(0, Math.min(current.chapters.length - 1, target))]?.start || 0);
}
function setRate(rate) {
  player.defaultPlaybackRate = player.playbackRate = rate;
  try { localStorage.setItem(prefsKey, JSON.stringify({ ...readJson(prefsKey), rate })); } catch { /* lasts for this page */ }
  paint();
}

function session() {
  if (!('mediaSession' in navigator) || !current) return;
  const chapter = current.chapters[chapterIndex(current, player.currentTime)];
  navigator.mediaSession.metadata = new MediaMetadata({ title: chapter?.title || current.title, artist: data.course.title, album: current.title });
  const actions = {
    play: () => player.play().catch(() => {}), pause: () => player.pause(),
    seekbackward: () => seek(player.currentTime - 15), seekforward: () => seek(player.currentTime + 30),
    previoustrack: () => chapterJump(-1), nexttrack: () => chapterJump(1),
    seekto: details => seek(details.seekTime),
  };
  for (const [action, handler] of Object.entries(actions)) { try { navigator.mediaSession.setActionHandler(action, handler); } catch { /* unsupported action */ } }
}
let sessionChapter = -1;
function paint() {
  if (current) {
    const index = chapterIndex(current, player.currentTime);
    if (index !== sessionChapter) { sessionChapter = index; session(); }
    if (Date.now() - savedAt > 5000 && !player.paused) remember();
  }
  dock?.paint(); if (view?.root.isConnected) view.paint(); else view = null;
}
function loop() { paint(); frame = player.paused ? 0 : requestAnimationFrame(loop); }
player.addEventListener('play', () => { if (!frame) frame = requestAnimationFrame(loop); paint(); });
player.addEventListener('pause', () => { remember(); paint(); });
for (const name of ['seeked', 'durationchange', 'loadedmetadata', 'ratechange']) player.addEventListener(name, paint);
player.addEventListener('ended', () => {
  const finished = current; remember(true);
  const shelf = shelfOf(finished), next = shelf[shelf.indexOf(finished) + 1];
  if (next) play(next, heard(next) && !heard(next).done ? undefined : 0); else paint();
});

function control(label, icon, handler, className = '') {
  const element = button('', handler, `audio-button ${className}`);
  element.setAttribute('aria-label', label); element.title = label; element.append(iconGlyph(icon));
  return element;
}
function skipControl(seconds) {
  const element = control(seconds < 0 ? `Back ${-seconds} seconds` : `Forward ${seconds} seconds`, seconds < 0 ? 'back' : 'ahead', () => seek(player.currentTime + seconds), 'audio-skip');
  element.append(node('span', 'audio-skip-label', String(Math.abs(seconds))));
  return element;
}
function setPlayControl(element, playing) {
  if (element.dataset.playing === String(playing)) return;
  element.dataset.playing = String(playing);
  const label = playing ? 'Pause' : 'Play';
  element.setAttribute('aria-label', label); element.title = label; element.replaceChildren(iconGlyph(playing ? 'pause' : 'play'));
}

// A seek bar split at the chapters, as on the video player; the gaps between segments map to
// the nearer chapter edge.
function seekBar(track, onSeek) {
  const bar = node('div', 'audio-seek'); bar.tabIndex = 0;
  for (const [name, value] of Object.entries({ role: 'slider', 'aria-label': 'Seek', 'aria-valuemin': 0, 'aria-valuemax': Math.round(track.duration) })) bar.setAttribute(name, value);
  const chapters = track.chapters.length ? track.chapters : [{ title: '', start: 0, end: track.duration }];
  const segments = chapters.map(chapter => {
    const segment = node('span', 'audio-segment');
    segment.style.setProperty('--a', chapter.start / track.duration); segment.style.setProperty('--b', chapter.end / track.duration);
    segment.style.flexGrow = chapter.end - chapter.start;
    return segment;
  });
  bar.append(append(node('span', 'audio-track'), ...segments));
  function timeAt(clientX) {
    const x = clientX - bar.getBoundingClientRect().left;
    for (const [index, segment] of segments.entries()) {
      const next = segments[index + 1], left = segment.offsetLeft, width = segment.offsetWidth;
      if (!next || x < left + width + (next.offsetLeft - left - width) / 2) {
        const { start, end } = chapters[index];
        return start + Math.min(1, Math.max(0, (x - left) / width)) * (end - start);
      }
    }
    return 0;
  }
  let scrubbing = false;
  bar.addEventListener('pointerdown', event => {
    if (event.button) return;
    event.preventDefault(); bar.setPointerCapture(event.pointerId); scrubbing = true; onSeek(timeAt(event.clientX));
  });
  bar.addEventListener('pointermove', event => { if (scrubbing) onSeek(timeAt(event.clientX)); });
  for (const name of ['pointerup', 'pointercancel']) bar.addEventListener(name, () => { scrubbing = false; });
  bar.addEventListener('keydown', event => {
    const now = position(track), index = chapterIndex(track, now);
    const target = { ArrowLeft: now - 5, ArrowDown: now - 5, ArrowRight: now + 5, ArrowUp: now + 5, Home: 0, End: track.duration,
      PageDown: chapters[Math.max(0, index - 1)].start, PageUp: chapters[Math.min(chapters.length - 1, index + 1)].start }[event.key];
    if (target === undefined) return;
    event.preventDefault(); event.stopPropagation(); onSeek(Math.max(0, Math.min(track.duration, target)));
  });
  bar.paint = now => {
    bar.style.setProperty('--played', now / track.duration);
    bar.setAttribute('aria-valuenow', Math.floor(now));
    bar.setAttribute('aria-valuetext', `${clock(now)} of ${clock(track.duration)}${chapters[chapterIndex(track, now)].title ? `, ${chapters[chapterIndex(track, now)].title}` : ''}`);
  };
  return bar;
}

// Where a chapter's teaching lives: its cheatsheet entry or pattern, or the Study passage.
function recallTarget(chapter) {
  for (const item of chapter.recall) {
    if (item.kind === 'concept' || item.kind === 'pattern') {
      const entry = (item.kind === 'concept' ? data.exam?.concepts : data.exam?.patterns)?.find(value => value.key === item.key);
      if (entry) return { href: `#exam/${item.kind === 'concept' ? 'sheet' : 'patterns'}/${entry.key}`, title: entry.title };
      continue;
    }
    const unit = data.units.find(value => value.key === item.unit), block = unit?.blocks[item.index];
    if (block?.title) return { href: `#study/${unit.key}/content/${block.key}`, title: block.title };
  }
  const unit = data.units.find(value => chapter.recall.some(item => item.unit === value.key));
  return unit ? { href: `#study/${unit.key}/content`, title: unit.title } : null;
}

function trackStatus(track) {
  if (updated(track)) return 'Updated';
  if (track === current && !player.paused) return 'Playing';
  const entry = heard(track);
  if (entry?.done) return 'Finished';
  return entry?.time > 5 ? `${minutes(track.duration - entry.time)} left` : '';
}

function libraryPage(missing) {
  const root = node('div', 'audio-workspace'), heading = node('h1', '', 'Audio');
  const header = append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading);
  root.append(header);
  if (missing) root.append(node('p', 'notice', 'That track is no longer here.'));
  if (!tracks.length) {
    root.append(node('p', '', data.hosted ? 'Audio notes play in the local app.' : 'No audio notes have been made for this course.'));
    return { root, heading, title: 'Audio', empty: true };
  }
  const total = tracks.reduce((sum, track) => sum + track.duration, 0);
  const download = node('a', 'audio-download small'); download.href = 'audio/playlist.zip'; download.download = '';
  download.append(iconGlyph('download'), node('span', '', 'Download playlist'));
  header.append(append(node('p', 'small audio-meta'), node('span', '', `${plural(tracks.length, 'track')} · ${minutes(total)}`), download));
  for (const [kind, label] of shelves) {
    const shelf = tracks.filter(track => track.kind === kind);
    if (!shelf.length) continue;
    const section = node('section', 'read-section audio-shelf'), title = node('h2', '', label);
    title.id = `audio-${kind}`; section.setAttribute('aria-labelledby', title.id);
    const all = button('', () => { const first = shelf.find(track => !heard(track)?.done) || shelf[0]; play(first); }, 'quiet audio-play-all');
    all.append(iconGlyph('play'), node('span', '', 'Play all'));
    section.append(append(node('div', 'section-heading'), title, all));
    const list = node('ul', 'topic-list');
    const rows = shelf.map(track => {
      const row = topicRow(trackLink(track), track.title, [`${minutes(track.duration)} · ${plural(track.chapters.length, 'chapter')}`], trackStatus(track));
      row.dataset.audioRow = track.stem;
      return row;
    });
    list.append(...rows); section.append(list); root.append(section);
  }
  const statuses = () => {
    for (const row of root.querySelectorAll('[data-audio-row]')) {
      const track = tracks.find(item => item.stem === row.dataset.audioRow), text = trackStatus(track);
      let status = row.querySelector('.topic-status');
      if (!text) { status?.remove(); continue; }
      if (!status) { status = node('span', 'small topic-status'); row.querySelector('a').append(status); }
      if (status.textContent !== text) status.textContent = text;
    }
  };
  view = { root, paint: statuses };
  return { root, heading, title: 'Audio' };
}

function trackPage(track) {
  const root = node('div', 'audio-workspace'); root.dataset.audioTrack = track.stem;
  const heading = studyText('h1', '', track.title), header = node('div', 'unit-header');
  const download = node('a', 'audio-download small'); download.href = track.track; download.download = '';
  download.append(iconGlyph('download'), node('span', '', 'Download'));
  header.append(node('p', 'eyebrow', shelfName(track)), heading,
    append(node('p', 'small audio-meta'), node('span', '', `${minutes(track.duration)} · ${plural(track.chapters.length, 'chapter')}`), download));
  if (updated(track)) header.append(node('p', 'notice', 'Updated since you last listened.'));
  root.append(header);

  const panel = node('section', 'audio-player'); panel.setAttribute('aria-label', 'Player');
  const bar = seekBar(track, seconds => { load(track); seek(seconds); });
  const time = node('span', 'audio-time'), chapterName = node('span', 'audio-chapter-name');
  const playButton = control('Play', 'play', () => toggle(track), 'audio-main');
  const speed = button('', () => { const rate = player.playbackRate; setRate(rates[(rates.indexOf(rate) + 1) % rates.length] || 1); }, 'audio-button audio-speed');
  speed.title = 'Playback speed';
  const jump = step => () => { load(track); chapterJump(step); };
  const back = skipControl(-15), ahead = skipControl(30);
  for (const element of [back, ahead]) element.addEventListener('click', () => load(track), { capture: true });
  panel.append(bar, append(node('div', 'audio-readout'), time, chapterName),
    append(node('div', 'audio-controls'), node('span', 'audio-gap'), control('Previous chapter', 'chapterBack', jump(-1)), back, playButton, ahead,
      control('Next chapter', 'chapterNext', jump(1)), append(node('span', 'audio-gap audio-gap-end'), speed)));
  // The video player's keys, while the player has focus: Space or k, j and l, the arrows.
  panel.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || (event.target.closest('button') && (event.key === ' ' || event.key === 'Enter'))) return;
    const action = { ' ': () => toggle(track), k: () => toggle(track), j: () => { load(track); seek(player.currentTime - 15); }, l: () => { load(track); seek(player.currentTime + 30); } }[event.key.length === 1 ? event.key.toLowerCase() : event.key];
    if (!action) return;
    event.preventDefault(); action();
  });
  root.append(panel);

  const chapterItems = track.chapters.map(chapter => {
    const item = node('li', 'audio-chapter');
    const go = button('', () => play(track, chapter.start), 'audio-chapter-go');
    go.append(node('span', 'audio-chapter-time', clock(chapter.start)), studyText('span', 'audio-chapter-title', chapter.title));
    item.append(go);
    const target = recallTarget(chapter);
    if (target) {
      const link = node('a', 'audio-recall small', 'Recall'); link.href = target.href;
      link.setAttribute('aria-label', `Recall: ${target.title}`); link.title = target.title;
      item.append(link);
    }
    return item;
  });
  if (chapterItems.length) root.append(append(node('section', 'read-section'), node('h2', '', 'Chapters'), append(node('ol', 'audio-chapters'), ...chapterItems)));

  const sentenceButtons = [];
  if (track.sentences.length) {
    const transcript = node('div', 'audio-transcript');
    for (const chapter of track.chapters) {
      const lines = track.sentences.filter(sentence => sentence.chapter === chapter.key);
      if (!lines.length) continue;
      const paragraph = node('p');
      for (const sentence of lines) {
        // Inline, so a sentence wraps like the text around it; Enter or Space plays from it.
        const line = studyText('span', 'audio-sentence', sentence.text), go = () => play(track, sentence.start);
        line.setAttribute('role', 'button'); line.tabIndex = 0;
        line.addEventListener('click', go);
        line.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); go(); } });
        sentenceButtons.push([sentence, line]); paragraph.append(line, ' ');
      }
      transcript.append(append(node('div', 'audio-passage'), studyText('p', 'eyebrow', chapter.title), paragraph));
    }
    root.append(append(node('section', 'read-section'), node('h2', '', 'Read along'), transcript));
  }
  const shelf = shelfOf(track), following = shelf[shelf.indexOf(track) + 1];
  if (following) root.append(nextStep({ href: trackLink(following), title: following.title, detail: `${shelfName(following)} · ${minutes(following.duration)}` }));

  let shownChapter = -1, shownSentence = null, shownText = '';
  function paintTrack() {
    const now = position(track), playing = track === current && !player.paused;
    bar.paint(now);
    const text = `${clock(now)} / ${clock(track.duration)}`;
    if (text !== shownText) { shownText = text; time.textContent = text; }
    setPlayControl(playButton, playing);
    const rate = track === current ? player.playbackRate : readJson(prefsKey).rate || 1;
    if (speed.textContent !== `${rate}×`) { speed.textContent = `${rate}×`; speed.setAttribute('aria-label', `Speed ${rate}×`); }
    const index = track.chapters.length ? chapterIndex(track, now) : -1;
    if (index !== shownChapter) {
      shownChapter = index; chapterName.textContent = track.chapters[index]?.title || '';
      chapterItems.forEach((item, position) => (position === index ? item.setAttribute('aria-current', 'true') : item.removeAttribute('aria-current')));
    }
    const active = track === current && player.currentTime > 0 ? sentenceButtons.find(([sentence], position) => now >= sentence.start - 0.15 && now < (sentenceButtons[position + 1]?.[0].start ?? Infinity) - 0.15) : null;
    if (active?.[1] !== shownSentence) {
      const previous = shownSentence, rect = previous?.getBoundingClientRect();
      // Follow along only while the student is looking at the passage being read.
      const watching = rect && rect.bottom > 0 && rect.top < innerHeight;
      previous?.removeAttribute('aria-current');
      shownSentence = active?.[1] || null;
      shownSentence?.setAttribute('aria-current', 'true');
      if (watching && shownSentence) shownSentence.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  }
  view = { root, paint: paintTrack };
  paintTrack();
  return { root, heading, title: track.title, current: track.stem };
}

function decode(value) { try { return decodeURIComponent(value || ''); } catch { return ''; } }
export function renderAudio(hash) {
  const key = decode(hash.split('/')[1]), track = tracks.find(item => item.stem === key);
  const page = track ? trackPage(track) : libraryPage(Boolean(key));
  queueMicrotask(syncDock);
  return page;
}
export function audioOutline(currentStem = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Audio');
  for (const track of shelves.flatMap(([kind]) => tracks.filter(item => item.kind === kind))) {
    const link = node('a', 'unit-link'); link.href = trackLink(track);
    link.append(node('span', 'small', `${shelfName(track)} · ${minutes(track.duration)}`), studyText('span', 'unit-title', track.title));
    if (track.stem === currentStem) link.setAttribute('aria-current', 'page');
    nav.append(link);
  }
  return nav;
}

// The mini player sits outside the app's page, so it keeps playing while the student moves
// between workspaces. It hides on the page of the track it is playing.
export function mountAudioDock() {
  if (dock || !tracks.length) return;
  dock = node('section', 'audio-dock'); dock.setAttribute('aria-label', 'Now playing'); dock.hidden = true;
  const progress = node('span', 'audio-dock-progress'), title = node('a', 'audio-dock-title');
  const name = node('span', 'audio-dock-name'), chapter = node('span', 'audio-dock-chapter small');
  title.append(name, chapter);
  const playButton = control('Play', 'play', () => current && toggle(current), 'audio-main');
  const close = control('Close player', 'close', () => { player.pause(); state.closed = true; saveState(); syncDock(); }, 'audio-close');
  dock.append(progress, title, append(node('div', 'audio-dock-controls'), skipControl(-15), playButton, control('Next chapter', 'chapterNext', () => chapterJump(1)), close));
  let shown = '';
  dock.paint = () => {
    if (!current) return;
    progress.style.setProperty('--played', player.currentTime / current.duration);
    setPlayControl(playButton, !player.paused);
    const parts = [current.title, current.chapters[chapterIndex(current, player.currentTime)]?.title || ''];
    if (parts.join('\n') !== shown) {
      shown = parts.join('\n'); [name.textContent, chapter.textContent] = parts;
      title.href = trackLink(current); title.setAttribute('aria-label', `${current.title}, open track`);
    }
    syncDock();
  };
  document.body.append(dock);
  // A reload keeps the last track ready where it stopped, paused, unless the student closed it.
  const last = tracks.find(track => track.stem === state.last);
  if (last && !state.closed) load(last);
  syncDock();
}
export function syncDock() {
  if (!dock) return;
  const visible = Boolean(current) && !state.closed && !document.querySelector(`[data-audio-track="${CSS.escape(current?.stem || '')}"]`);
  if (dock.hidden === visible) dock.hidden = !visible;
  document.documentElement.toggleAttribute('data-audio-dock', visible);
}
