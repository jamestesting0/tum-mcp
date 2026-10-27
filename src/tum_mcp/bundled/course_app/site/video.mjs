import data from './data.mjs';
import { node, append, button } from './dom.mjs';

// Videos are a local-preview feature: hosted sites never request the index.
async function loadIndex() {
  if (data.hosted) return {};
  try {
    const response = await fetch('videos/index.json', { cache: 'no-store', signal: AbortSignal.timeout(2000) });
    if (!response.ok) return {};
    const value = await response.json();
    return value && typeof value.videos === 'object' && value.videos ? value.videos : {};
  } catch {
    return {};
  }
}

const videos = await loadIndex();

function clock(seconds) {
  // Floor like media players and the generated README, so the same time reads the same.
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

export function videoPanel(unit) {
  const entry = videos[unit.key];
  if (!entry) return null;
  const section = node('section', 'video-note');
  const heading = node('h2', '', 'Video explainer');
  heading.id = `video-${unit.key}`;
  section.setAttribute('aria-labelledby', heading.id);
  section.append(append(node('div', 'section-heading'), heading, node('span', 'small video-length', clock(entry.duration))));
  if (entry.madeForRevision !== unit.revision) {
    section.append(node('p', 'notice', 'This video was made for an earlier version of this topic. The text below is current.'));
  }
  const video = node('video');
  Object.assign(video, { controls: true, preload: 'none', playsInline: true, poster: entry.poster });
  video.setAttribute('aria-label', `Video explainer: ${entry.title}`);
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
