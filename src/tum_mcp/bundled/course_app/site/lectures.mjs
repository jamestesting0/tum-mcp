import data from './data.mjs';
import { node, studyText, append, sourcesNote } from './dom.mjs';
import { renderCommentedView } from './comments.mjs';

const lectures = [...(data.lectures?.lectures || [])].sort((a, b) => b.recording.recorded_on.localeCompare(a.recording.recorded_on) || a.key.localeCompare(b.key));
export const lectureLink = (lecture, highlight) => `#lectures/${encodeURIComponent(lecture.key)}${highlight ? `/${encodeURIComponent(highlight.key)}` : ''}`;
function date(value) {
  const day = new Date(value.length === 10 ? value + 'T12:00:00Z' : value);
  return Number.isFinite(day.getTime()) ? new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(day) : 'Date unavailable';
}
export function clock(value) {
  const seconds = Math.floor(value), h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60;
  return `${h ? h + ':' + String(m).padStart(2, '0') : m}:${String(seconds % 60).padStart(2, '0')}`;
}
const duration = seconds => seconds < 60 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
const watchTime = lecture => lecture.highlights.reduce((total, item) => total + item.interval.end_s - item.interval.start_s, 0);
function timeLink(url, start, end) {
  const link = node('a', 'lecture-time small', `${clock(start)}${end == null ? '' : '–' + clock(end)}`);
  link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  link.setAttribute('aria-label', `Open recording at ${link.textContent}`);
  return link;
}
export function lectureOutline(current = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Lecture');
  for (const lecture of lectures) {
    const link = node('a', 'unit-link'); link.href = lectureLink(lecture);
    link.append(node('span', 'small', date(lecture.recording.recorded_on)), studyText('span', 'unit-title', lecture.title));
    if (lecture.key === current) link.setAttribute('aria-current', 'page');
    nav.append(link);
  }
  return nav;
}
function decode(value) { try { return decodeURIComponent(value || ''); } catch { return ''; } }
function noteView(note, active) {
  const root = node('li', 'lecture-note'); root.dataset.lectureSection = note.key; root.dataset.commentTarget = 'lectures'; root.tabIndex = -1;
  if (active) root.dataset.lectureActiveSection = '';
  const sources = [...new Set([...note.sources, note.recording_source])];
  const provenance = { [note.recording_source]: [timeLink(note.url, note.at_s)] };
  root.append(append(node('div', 'lecture-note-row'), studyText('p', 'lecture-note-text', note.text),
    sourcesNote(sources, data.sources, data.course.synthetic, '', provenance, note.pages || '')));
  if (note.image) {
    const image = node('img', 'lecture-note-image');
    Object.assign(image, { src: note.image.asset, alt: note.image.alt, width: note.image.width, height: note.image.height, loading: 'lazy', decoding: 'async' });
    root.append(image);
  }
  return root;
}
function highlightView(highlight, active) {
  const root = node('section', 'read-section lecture-highlight'); root.dataset.lectureSection = highlight.key; root.dataset.commentTarget = 'lectures';
  if (active) root.dataset.lectureActiveSection = '';
  // The frame opens the same moment as the time link beside it, so it stays out of the tab order.
  const thumb = node('a', 'lecture-thumb'); thumb.href = highlight.url; thumb.target = '_blank'; thumb.rel = 'noopener noreferrer';
  thumb.tabIndex = -1; thumb.setAttribute('aria-hidden', 'true');
  const image = node('img');
  Object.assign(image, { src: highlight.thumbnail.asset, alt: '', width: highlight.thumbnail.width, height: highlight.thumbnail.height, loading: 'lazy', decoding: 'async' });
  image.addEventListener('error', () => { thumb.hidden = true; });
  thumb.append(image);
  const heading = append(node('div', 'section-heading'), studyText('h3', '', highlight.title));
  if (highlight.sources.length) heading.append(sourcesNote(highlight.sources, data.sources, data.course.synthetic, highlight.title, {}, highlight.pages || ''));
  const { start_s: start, end_s: end } = highlight.interval;
  const body = append(node('div', 'lecture-highlight-body'), heading,
    append(node('p', 'lecture-when small'), timeLink(highlight.url, start, end), ` · ${duration(end - start)}`),
    studyText('p', 'lecture-teaches', highlight.teaches));
  if (highlight.points.length) body.append(append(node('ul', 'lecture-points'), ...highlight.points.map(text => studyText('li', '', text))));
  root.append(thumb, body);
  return root;
}
export function renderLectures(hash) {
  const [, key, highlightKey] = hash.split('/'), lecture = lectures.find(item => item.key === decode(key));
  const root = node('div', 'lecture-workspace');
  if (!lecture) {
    const heading = node('h1', '', 'Lecture');
    root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading));
    if (key) root.append(node('p', 'notice', 'That lecture is no longer here. Choose a prepared lecture below.'));
    if (!lectures.length) root.append(node('p', '', 'Lecture content has not been prepared for this course.'));
    const list = node('ul', 'topic-list');
    for (const item of lectures) {
      const link = node('a'); link.href = lectureLink(item);
      const parts = [];
      if (item.notes.length) parts.push(`${item.notes.length} note${item.notes.length === 1 ? '' : 's'}`);
      if (item.highlights.length) parts.push(`${item.highlights.length} highlight${item.highlights.length === 1 ? '' : 's'}`, `${duration(watchTime(item))} of ${duration(item.recording.duration_s)}`);
      const count = parts.join(' · ') || 'No lecture additions';
      link.append(append(node('span', 'topic-copy'), studyText('span', 'topic-title', item.title), node('span', 'small', date(item.recording.recorded_on)), studyText('span', 'small', item.summary), node('span', 'small lecture-count', count)));
      list.append(append(node('li', 'topic-row'), link));
    }
    root.append(list); return { root, heading, title: 'Lecture' };
  }
  const heading = studyText('h1', '', lecture.title), header = node('div', 'unit-header');
  header.append(node('p', 'eyebrow', date(lecture.recording.recorded_on)), heading, studyText('p', 'unit-summary', lecture.summary));
  header.append(node('p', 'small lecture-meta', `${lecture.coverage.status === 'complete' ? '' : 'Partial coverage · '}Sources checked ${date(lecture.evidence_as_of)}`));
  // The Study topics that teach this lecture, so highlights and lessons lead to each other.
  const taught = data.units.filter(unit => (unit.lectures || []).includes(lecture.key));
  if (taught.length) {
    const line = append(node('p', 'small related-work'), node('span', 'related-label', 'Study: '));
    taught.forEach((unit, index) => { if (index) line.append(', '); const link = studyText('a', '', unit.title); link.href = `#study/${unit.key}/content`; line.append(link); });
    header.append(line);
  }
  if (lecture.coverage.status !== 'complete') {
    const coverage = node('details', 'disclosure plain lecture-coverage small');
    coverage.append(node('summary', '', 'Coverage'));
    const missing = lecture.coverage.missing || [], uncertain = lecture.coverage.uncertain || [];
    coverage.append(node('p', '', 'Some passages are missing or need review.'));
    for (const [label, spans] of [['Missing', missing], ['Unclear speech', uncertain]]) {
      for (const span of spans) coverage.append(node('p', '', `${label}: ${clock(span.start_s)}–${clock(span.end_s)}`));
    }
    header.append(coverage);
  }
  root.append(header);
  const active = decode(highlightKey);
  if (highlightKey && ![...lecture.notes, ...lecture.highlights].some(item => item.key === active)) root.append(node('p', 'notice', 'That lecture passage is no longer here.'));
  if (lecture.notes.length) {
    const notes = append(node('section', 'lecture-notes read-section'), node('h2', '', 'Notes'));
    notes.append(append(node('ul', 'lecture-note-list'), ...lecture.notes.map(note => noteView(note, note.key === active))));
    root.append(notes);
  }
  if (lecture.highlights.length) {
    const highlights = append(node('section', 'lecture-highlights read-section'), node('h2', '', 'Highlights'));
    for (const highlight of lecture.highlights) highlights.append(highlightView(highlight, highlight.key === active));
    root.append(highlights);
  }
  if (!lecture.notes.length && !lecture.highlights.length) root.append(node('p', 'small', 'No additional notes or highlights were selected from this lecture.'));
  const comments = renderCommentedView(lecture, 'lectures', root);
  return { root: comments.root, heading, title: lecture.title, current: lecture.key, lecture };
}
