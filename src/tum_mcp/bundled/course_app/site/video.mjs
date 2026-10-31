import data from './data.mjs';
import { node, append, button } from './dom.mjs';

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
  if (solution) solution.append(slot);
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
        (solution ? slot : details).append(made);
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
    section.append(node('p', 'notice', 'This video was made for an earlier version of this topic or problem. The prepared text is current.'));
  }
  const video = node('video');
  Object.assign(video, { controls: true, preload: 'none', playsInline: true, poster: entry.poster });
  video.setAttribute('aria-label', `${title || 'Video solution'}: ${entry.title}`);
  const source = node('source'); source.src = entry.track; source.type = 'video/mp4';
  const track = node('track');
  Object.assign(track, { kind: 'captions', src: entry.captions, srclang: entry.language, label: 'Captions' });
  video.append(source, track);
  section.append(video);
  if (entry.chapters.length > 1) {
    const list = node('ol', 'video-chapters');
    list.setAttribute('aria-label', 'Chapters');
    for (const chapter of entry.chapters) {
      const jump = button(`${clock(chapter.start)} ${chapter.title}`, () => {
        video.currentTime = chapter.start;
        video.play().catch(() => {});
        video.focus();
      }, 'quiet');
      list.append(append(node('li'), jump));
    }
    section.append(list);
  }
  const links = node('p', 'small video-links');
  const transcript = node('a', '', 'Transcript'); transcript.href = entry.transcript;
  links.append(transcript);
  if (!entry.narrated) links.append(' · Synthetic preview without narration');
  section.append(links);
  return section;
}
