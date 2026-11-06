import data from '../../data.mjs';
import { node, append, button } from '../shell/dom.mjs';
import { iconGlyph } from '../shell/navigation.mjs';

// Videos are a local-preview feature: hosted sites never request the index. The index loads
// beside the app rather than holding it back, so a busy server only delays the video panel.
let videos = null;
let index = null;
function loadIndex() {
  if (!index) index = (data.hosted ? Promise.resolve({}) : fetch('videos/index.json', { cache: 'no-store', signal: AbortSignal.timeout(30000) })
    .then(response => (response.ok ? response.json() : {}))
    .catch(() => ({})))
    .then(value => {
      videos = { videos: value?.videos || {}, exercises: value?.exercises || {} };
      return videos;
    });
  return index;
}

function clock(seconds) {
  // Floor like media players and the generated README, so the same time reads the same.
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

// The panel when the index is known; until then a placeholder that becomes the panel, or goes.
export function videoPanel(unit) {
  if (videos) return panel(unit);
  const slot = node('div', 'video-slot');
  loadIndex().then(() => { const made = panel(unit); if (made) slot.replaceWith(made); else slot.remove(); });
  return slot;
}

function panel(unit) {
  const entry = videos.videos[unit.key];
  if (!entry) return null;
  return player(entry, unit, 'Video explainer');
}

// A walkthrough is mounted only inside an opened Solution, never into the Exam caller.
export function exerciseVideo(exercise, identity, solution = null) {
  const slot = node('div', 'video-slot');
  // Inside an opened Solution the video joins its panel; on its own it gets a panel of its own.
  if (solution) (solution.querySelector(':scope > .disclosure-panel') || solution).append(slot);
  loadIndex().then(() => {
    const entry = videos.exercises[identity];
    if (!entry) { slot.remove(); return; }
    const details = solution || node('details', 'disclosure exercise-disclosure');
    if (!solution) {
      const summary = node('summary', '', 'Video solution (all parts)');
      summary.dataset.contentsEntry = '';
      details.append(summary);
      slot.append(details);
    }
    let made = null;
    function toggle() {
      if (details.open && !made) {
        made = player(entry, { ...exercise, revision: exercise.videoRevision }, solution ? 'Video solution' : null);
        if (solution) slot.append(made); else details.append(append(node('div', 'disclosure-panel'), made));
      } else if (!details.open && made) made.querySelector('video').pause();
    }
    details.addEventListener('toggle', toggle);
    toggle();
  });
  return slot;
}

function player(entry, item, title) {
  const section = node('section', 'video-note');
  if (title) {
    const heading = node('h2', '', title);
    heading.id = `video-${item.key}`;
    section.setAttribute('aria-labelledby', heading.id);
    section.append(append(node('div', 'section-heading'), heading, node('span', 'small video-length', clock(entry.duration))));
  }
  if (entry.sourceStale || entry.madeForRevision !== item.revision) {
    section.append(node('p', 'notice', 'This video was made for an earlier version; the text is current.'));
  }
  const video = node('video');
  Object.assign(video, { preload: 'none', playsInline: true, poster: entry.poster });
  video.setAttribute('aria-label', `${title || 'Video solution'}: ${entry.title}`);
  const source = node('source'); source.src = entry.track; source.type = 'video/mp4';
  const track = node('track');
  Object.assign(track, { kind: 'captions', src: entry.captions, srclang: entry.language, label: 'Captions' });
  video.append(source, track);
  section.append(controlled(video, track, entry));
  const links = node('p', 'small video-links');
  const transcript = node('a', '', 'Transcript'); transcript.href = entry.transcript;
  links.append(transcript);
  if (!entry.narrated) links.append(' · Synthetic preview without narration');
  section.append(links);
  return section;
}

const rates = [1, 1.25, 1.5, 1.75, 2, 0.75], prefsKey = 'study-space:player';
function prefs() { try { return JSON.parse(localStorage.getItem(prefsKey)) || {}; } catch { return {}; } }
function remember(change) { try { localStorage.setItem(prefsKey, JSON.stringify({ ...prefs(), ...change })); } catch { /* lasts for this page */ } }
function control(label, icon, handler, className) {
  const element = button('', handler, `player-button ${className}`);
  element.setAttribute('aria-label', label); element.title = label; element.append(iconGlyph(icon));
  return element;
}
function setControl(element, label, icon) { element.setAttribute('aria-label', label); element.title = label; element.replaceChildren(iconGlyph(icon)); }

// A minimal player: the picture, a seek bar split at the chapters and one row of controls that fades
// while the video plays. Captions are drawn by the app so they rise above the controls.
function controlled(video, track, entry) {
  const root = node('div', 'player'); root.tabIndex = -1;
  const length = () => (video.duration > 0 && Number.isFinite(video.duration) ? video.duration : entry.duration);
  // A video without chapters plays as one whole segment.
  const chapters = (entry.chapters.length ? entry.chapters : [{ title: '', start: 0 }]).map((chapter, index, all) => ({ title: chapter.title, start: index ? chapter.start : 0, end: all[index + 1]?.start ?? entry.duration }));
  const titled = chapters.length > 1;
  const at = time => { let index = 0; while (index + 1 < chapters.length && time >= chapters[index + 1].start) index++; return index; };

  const seek = node('div', 'player-seek');
  Object.entries({ role: 'slider', 'aria-label': 'Seek', 'aria-valuemin': 0, 'aria-valuemax': Math.round(entry.duration) }).forEach(([name, value]) => seek.setAttribute(name, value));
  seek.tabIndex = 0;
  const segments = chapters.map(chapter => {
    const segment = node('span', 'player-segment');
    segment.style.setProperty('--a', chapter.start / entry.duration); segment.style.setProperty('--b', chapter.end / entry.duration);
    segment.style.flexGrow = chapter.end - chapter.start;
    return segment;
  });
  const thumb = node('span', 'player-thumb'), tipTitle = node('span', 'player-tip-title'), tipTime = node('span', 'player-tip-time');
  const tip = append(node('span', 'player-tip'), tipTitle, tipTime);
  seek.append(append(node('span', 'player-track'), ...segments), thumb, tip);

  const toggle = () => (video.paused ? video.play().catch(() => {}) : video.pause());
  const play = control('Play', 'play', toggle, 'player-play'), big = control('Play', 'play', toggle, 'player-big');
  const mute = control('Mute', 'volume', () => { video.muted = !video.muted; }, 'player-mute');
  const time = node('span', 'player-time'), current = node('span', 'player-chapter');
  const speed = button('', () => setRate(rates[(rates.indexOf(video.playbackRate) + 1) % rates.length], true), 'player-button player-speed');
  const captionsButton = control('Captions', 'captions', () => setCaptions(!captions, true), 'player-captions');
  const full = control('Full screen', 'expand', fullscreen, 'player-full');
  const caption = node('div', 'player-caption'), spinner = node('div', 'player-spinner');
  caption.setAttribute('aria-hidden', 'true');
  root.append(video, caption, spinner, big, append(node('div', 'player-controls'), seek,
    append(node('div', 'player-bar'), play, mute, time, current, node('span', 'player-gap'), speed, captionsButton, full)));

  // Segment geometry, for the thumb and for mapping a pointer to a time across the gaps.
  let geometry = [];
  new ResizeObserver(() => { geometry = segments.map(segment => [segment.offsetLeft, segment.offsetWidth]); paint(); }).observe(seek);
  function timeAt(clientX) {
    const x = clientX - seek.getBoundingClientRect().left;
    for (const [index, [left, width]] of geometry.entries()) {
      const next = geometry[index + 1];
      if (!next || x < left + width + (next[0] - left - width) / 2) {
        const { start, end } = chapters[index];
        return start + Math.min(1, Math.max(0, (x - left) / width)) * (end - start);
      }
    }
    return 0;
  }
  function xAt(time) {
    const index = at(time), [left, width] = geometry[index] || [0, 0], { start, end } = chapters[index];
    return left + width * Math.min(1, Math.max(0, (time - start) / (end - start)));
  }

  let scrubbing = false, scrubTime = 0, shown = '', chapter = -1, frame = 0, pendingSeek = 0, idle = 0, captions = false, hovered = -1;
  function paint() {
    const now = scrubbing ? scrubTime : video.currentTime, total = length();
    seek.style.setProperty('--played', now / entry.duration);
    thumb.style.transform = `translateX(${xAt(now)}px)`;
    const text = `${clock(now)} / ${clock(total)}`;
    if (text !== shown) {
      shown = text; time.textContent = text;
      seek.setAttribute('aria-valuenow', Math.floor(now));
      seek.setAttribute('aria-valuetext', `${clock(now)} of ${clock(total)}${titled ? `, ${chapters[at(now)].title}` : ''}`);
    }
    if (at(now) !== chapter) {
      chapter = at(now);
      if (titled) current.textContent = chapters[chapter].title;
    }
  }
  function loop() { paint(); frame = video.paused ? 0 : requestAnimationFrame(loop); }
  function seekTo(seconds) { video.currentTime = Math.max(0, Math.min(length(), seconds)); paint(); }
  function wake() {
    delete root.dataset.idle; clearTimeout(idle);
    idle = setTimeout(() => { if (!video.paused && !scrubbing) root.dataset.idle = ''; }, 2500);
  }
  function setRate(rate, save) {
    video.defaultPlaybackRate = video.playbackRate = rate;
    speed.textContent = `${rate}×`; speed.setAttribute('aria-label', `Speed ${rate}×`); speed.title = 'Playback speed';
    if (save) remember({ rate });
  }
  function showCues() { caption.replaceChildren(...[...(track.track.activeCues || [])].map(cue => append(node('span'), cue.getCueAsHTML()))); }
  function setCaptions(on, save) {
    captions = on; track.track.mode = on ? 'hidden' : 'disabled';
    captionsButton.setAttribute('aria-pressed', String(on));
    if (on) showCues(); else caption.replaceChildren();
    if (save) remember({ captions: on });
  }
  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (root.requestFullscreen) root.requestFullscreen().catch(() => {});
    else video.webkitEnterFullscreen?.();
  }

  video.addEventListener('play', () => {
    root.dataset.started = ''; root.dataset.playing = ''; setControl(play, 'Pause', 'pause');
    if (!frame) frame = requestAnimationFrame(loop);
    wake();
  });
  video.addEventListener('pause', () => { delete root.dataset.playing; delete root.dataset.waiting; setControl(play, 'Play', 'play'); wake(); paint(); });
  for (const name of ['timeupdate', 'seeked', 'durationchange']) video.addEventListener(name, () => { if (video.paused) paint(); });
  video.addEventListener('waiting', () => { root.dataset.waiting = ''; });
  for (const name of ['playing', 'canplay', 'seeked']) video.addEventListener(name, () => { delete root.dataset.waiting; });
  video.addEventListener('progress', () => {
    const ranges = video.buffered;
    for (let index = 0; index < ranges.length; index++) {
      if (ranges.start(index) <= video.currentTime + 0.5 && video.currentTime <= ranges.end(index)) seek.style.setProperty('--buffered', ranges.end(index) / entry.duration);
    }
  });
  video.addEventListener('volumechange', () => setControl(mute, video.muted ? 'Unmute' : 'Mute', video.muted ? 'muted' : 'volume'));
  track.track.addEventListener('cuechange', () => { if (captions) showCues(); });
  root.addEventListener('fullscreenchange', () => {
    const on = document.fullscreenElement === root;
    setControl(full, on ? 'Exit full screen' : 'Full screen', on ? 'shrink' : 'expand');
  });

  // A mouse click plays or pauses; a tap first shows the controls, as on a phone's own player.
  let pointer = 'mouse';
  root.addEventListener('pointerdown', event => { pointer = event.pointerType; }, true);
  root.addEventListener('pointermove', event => { if (event.pointerType === 'mouse') wake(); });
  root.addEventListener('pointerleave', () => { if (!video.paused && !scrubbing) root.dataset.idle = ''; });
  video.addEventListener('click', () => {
    if (pointer === 'mouse' || video.paused) toggle();
    else if ('idle' in root.dataset) wake();
    else root.dataset.idle = '';
  });
  video.addEventListener('dblclick', () => { if (pointer === 'mouse') fullscreen(); });

  function hover(seconds) {
    tipTitle.textContent = titled ? chapters[at(seconds)].title : ''; tipTime.textContent = clock(seconds);
    const half = tip.offsetWidth / 2, width = seek.clientWidth;
    tip.style.transform = `translateX(${Math.min(width - half, Math.max(half, xAt(seconds))) - half}px)`;
    seek.dataset.hover = '';
    if (at(seconds) !== hovered) { hovered = at(seconds); segments.forEach((segment, index) => segment.classList.toggle('hovered', index === hovered)); }
  }
  function unhover() { delete seek.dataset.hover; hovered = -1; segments.forEach(segment => segment.classList.remove('hovered')); }
  function scrubTo(seconds) {
    scrubTime = seconds; paint();
    if (!pendingSeek) pendingSeek = requestAnimationFrame(() => { pendingSeek = 0; if (scrubbing) video.currentTime = scrubTime; });
  }
  seek.addEventListener('pointerdown', event => {
    if (event.button) return;
    event.preventDefault(); seek.setPointerCapture(event.pointerId);
    scrubbing = true; root.dataset.scrubbing = ''; wake(); hover(timeAt(event.clientX)); scrubTo(timeAt(event.clientX));
  });
  seek.addEventListener('pointermove', event => {
    if (scrubbing) { hover(timeAt(event.clientX)); scrubTo(timeAt(event.clientX)); } else if (event.pointerType === 'mouse') hover(timeAt(event.clientX));
  });
  const release = event => {
    if (!scrubbing) return;
    scrubbing = false; delete root.dataset.scrubbing; seekTo(scrubTime); wake();
    if (event.pointerType !== 'mouse') unhover();
  };
  seek.addEventListener('pointerup', release); seek.addEventListener('pointercancel', release);
  seek.addEventListener('pointerleave', () => { if (!scrubbing) unhover(); });
  seek.addEventListener('keydown', event => {
    const now = video.currentTime, index = at(now), back = now - chapters[index].start < 2 ? Math.max(0, index - 1) : index;
    const target = { ArrowLeft: now - 5, ArrowDown: now - 5, ArrowRight: now + 5, ArrowUp: now + 5, Home: 0, End: length(),
      PageDown: chapters[back].start, PageUp: chapters[Math.min(chapters.length - 1, index + 1)].start }[event.key];
    if (target === undefined) return;
    event.preventDefault(); event.stopPropagation(); seekTo(target); wake();
  });
  // YouTube's keys, while the player has focus: k or Space, j and l, the arrows, f, m and c.
  root.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target.closest('button') && (event.key === ' ' || event.key === 'Enter')) return;
    const action = { ' ': toggle, k: toggle, j: () => seekTo(video.currentTime - 10), l: () => seekTo(video.currentTime + 10),
      ArrowLeft: () => seekTo(video.currentTime - 5), ArrowRight: () => seekTo(video.currentTime + 5),
      f: fullscreen, m: () => { video.muted = !video.muted; }, c: () => setCaptions(!captions, true) }[event.key.length === 1 ? event.key.toLowerCase() : event.key];
    if (!action) return;
    event.preventDefault(); action(); wake();
  });

  const saved = prefs();
  setRate(rates.includes(saved.rate) ? saved.rate : 1, false);
  setCaptions(saved.captions === true, false);
  paint();
  return root;
}
