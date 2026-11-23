import data from '../../data.mjs';
import { node, studyText, append, button, sourcesNote, topicRow } from '../shell/dom.mjs';
import { openReference } from '../shell/reference-panel.mjs';
import { renderCommentedView } from '../comments/comments.mjs';
import { nextStep } from '../shell/navigation.mjs';
import { renderBlockBody } from '../reading/reading.mjs';

const sorted = () => [...(data.lectures?.lectures || [])].sort((a, b) => b.recording.recorded_on.localeCompare(a.recording.recorded_on) || a.key.localeCompare(b.key));
let lectures = sorted();
// An Ask agent edit swaps the course data in place; the redraw that follows reads the new list.
addEventListener('course-data', () => { lectures = sorted(); });
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
function previewImage(src) {
  const image = node('img', 'lecture-preview');
  Object.assign(image, { src, alt: '', loading: 'lazy', decoding: 'async' });
  image.addEventListener('error', () => image.remove(), { once: true });
  return image;
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
// The Study passage that teaches an entry's subject, opened beside the page.
function recallButton(passage) {
  const unit = passage && data.units.find(item => item.key === passage.unit);
  const block = unit?.blocks.find(item => item.key === passage.block);
  if (!block) return null;
  const recall = button('', () => openReference(unit, block, recall), 'term-more lecture-recall');
  recall.append(studyText('span', '', `Recall: ${block.title || unit.title}`));
  return recall;
}
// The explanation's stages, each opening the recording at its own moment; consecutive
// steps of one subgoal sit under its label and the numbering runs on across them.
function highlightSteps(steps) {
  const root = node('div', 'lecture-step-groups');
  let list = null;
  steps.forEach((step, index) => {
    if (!list || step.subgoal !== steps[index - 1].subgoal) {
      if (step.subgoal) root.append(studyText('p', 'eyebrow lecture-step-subgoal', step.subgoal));
      list = node('ol', 'lecture-steps'); list.start = index + 1; root.append(list);
    }
    const item = node('li');
    item.append(append(node('p', 'lecture-step-action'), timeLink(step.url, step.at), ' ', studyText('span', '', step.action)), studyText('p', 'lecture-step-why', step.why));
    if (step.note) item.append(append(node('p', 'walk-note'), node('strong', '', 'Pitfall: '), studyText('span', '', step.note)));
    list.append(item);
  });
  return root;
}
function noteView(note, active) {
  const root = node('li', 'lecture-note'); root.dataset.lectureSection = note.key; root.dataset.commentTarget = 'lectures'; root.tabIndex = -1;
  if (active) root.dataset.lectureActiveSection = '';
  const sources = [...new Set([...note.sources, note.recording_source])];
  // What kind of remark, what it is about, the situation it answers, the message, then the
  // working the lecturer gave; the moment in the recording is shown once, beside Recall.
  const head = append(node('div', 'lecture-note-head'), studyText('p', 'lecture-note-title', note.title),
    sourcesNote(sources, data.sources, data.course.synthetic, note.title, {}, note.pages || ''));
  // Only a correction or an exam instruction is labelled: those change what the student does.
  if (note.kind) root.append(node('p', 'block-label lecture-note-kind', note.kind[0].toUpperCase() + note.kind.slice(1)));
  root.append(head, studyText('p', 'lecture-note-context', note.context), studyText('p', 'lecture-note-text', note.text));
  if (note.steps?.length) root.append(append(node('ol', 'steps lecture-note-steps'), ...note.steps.map(text => studyText('li', '', text))));
  if (note.points?.length) root.append(append(node('ul', 'lecture-note-points'), ...note.points.map(text => studyText('li', '', text))));
  for (const block of note.blocks || []) root.append(renderBlockBody(block));
  if (note.image) {
    const image = node('img', 'lecture-note-image');
    Object.assign(image, { src: note.image.asset, alt: note.image.alt, width: note.image.width, height: note.image.height, loading: 'lazy', decoding: 'async' });
    root.append(image);
  }
  const foot = append(node('p', 'lecture-note-foot small'), append(node('span'), 'Watch ', timeLink(note.url, note.at_s)));
  const recall = recallButton(note.passage);
  if (recall) foot.append(recall);
  root.append(foot);
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
  thumb.append(image, node('span', 'lecture-thumb-time small', duration(highlight.interval.end_s - highlight.interval.start_s)));
  const heading = append(node('div', 'section-heading'), studyText('h3', '', highlight.title));
  if (highlight.sources.length) heading.append(sourcesNote(highlight.sources, data.sources, data.course.synthetic, highlight.title, {}, highlight.pages || ''));
  const { start_s: start, end_s: end } = highlight.interval;
  const body = append(node('div', 'lecture-highlight-body'), heading,
    append(node('p', 'lecture-when small'), timeLink(highlight.url, start, end), ` · ${duration(end - start)}`));
  // The frame sits beside the title and time; what the passage teaches reads at full width below.
  const text = append(node('div', 'lecture-highlight-text'), studyText('p', 'lecture-teaches', highlight.teaches));
  if (highlight.points.length) text.append(append(node('ul', 'lecture-points'), ...highlight.points.map(item => studyText('li', '', item))));
  if (highlight.steps?.length) text.append(highlightSteps(highlight.steps));
  const recall = recallButton(highlight.passage);
  if (recall) text.append(recall);
  root.append(thumb, body, text);
  return root;
}
// Stretches of the recording without usable speech, each shown once where it occurs.
function gaps(lecture) {
  const spans = [['Audio unavailable', lecture.coverage.missing || []], ['Unclear audio', lecture.coverage.uncertain || []]];
  return spans.flatMap(([label, list]) => list.map(span => ({
    start: span.start_s,
    row: node('p', 'small lecture-gap', `${label} ${clock(span.start_s)}–${clock(span.end_s)}`),
  }))).sort((a, b) => a.start - b.start);
}
// The lecture as its topics in recording order: each chapter holds its notes, highlights and gaps.
function lectureChapters(lecture, chapters, active) {
  const entries = [
    ...lecture.notes.map(note => ({ start: note.at_s, note })),
    ...lecture.highlights.map(highlight => ({ start: highlight.interval.start_s, highlight })),
    ...gaps(lecture),
  ].sort((a, b) => a.start - b.start);
  const inside = (chapter, start) => chapter.interval.start_s <= start && start < chapter.interval.end_s;
  // Anything outside every chapter (a gap during a break) is shown on its own.
  const view = entry => entry.row || (entry.highlight ? highlightView(entry.highlight, entry.highlight.key === active)
    : append(node('ul', 'lecture-note-list'), noteView(entry.note, entry.note.key === active)));
  const parts = [];
  let next = 0;
  for (const chapter of chapters) {
    // A gap between chapters (a break, a lost stretch) stands where it happened.
    while (next < entries.length && entries[next].start < chapter.interval.start_s) parts.push(view(entries[next++]));
    const section = node('section', 'read-section lecture-chapter');
    section.dataset.lectureSection = chapter.key;
    if (chapter.key === active) section.dataset.lectureActiveSection = '';
    const heading = append(node('div', 'section-heading'), studyText('h2', '', chapter.title));
    if (chapter.sources?.length) heading.append(sourcesNote(chapter.sources, data.sources, data.course.synthetic, chapter.title, {}, chapter.pages || ''));
    const time = timeLink(chapter.url, chapter.interval.start_s, chapter.interval.end_s);
    time.setAttribute('aria-label', `Watch ${chapter.title} at ${clock(chapter.interval.start_s)}`);
    const header = node('div', 'lecture-chapter-head');
    if (chapter.slide_preview) {
      const link = node('a', 'lecture-chapter-preview');
      Object.assign(link, { href: chapter.url, target: '_blank', rel: 'noopener noreferrer', tabIndex: -1 });
      link.setAttribute('aria-hidden', 'true');
      link.title = `Course material, page ${chapter.preview_page || chapter.pages.split('-')[0]}`;
      link.append(previewImage(chapter.slide_preview));
      header.append(link);
    }
    header.append(append(node('div', 'lecture-chapter-copy'), heading,
      append(node('p', 'lecture-chapter-time small'), time)));
    section.append(header);
    let notes = null;
    while (next < entries.length && inside(chapter, entries[next].start)) {
      const entry = entries[next++];
      if (entry.note) {
        if (!notes) { notes = node('ul', 'lecture-note-list'); section.append(notes); }
        notes.append(noteView(entry.note, entry.note.key === active));
        continue;
      }
      notes = null;
      section.append(entry.highlight ? highlightView(entry.highlight, entry.highlight.key === active) : entry.row);
    }
    parts.push(section);
  }
  while (next < entries.length) parts.push(view(entries[next++]));
  return parts;
}
export function renderLectures(hash) {
  const [, key, highlightKey] = hash.split('/'), lecture = lectures.find(item => item.key === decode(key));
  const root = node('div', 'lecture-workspace');
  if (!lecture) {
    const heading = node('h1', '', 'Lecture');
    root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading));
    if (key) root.append(node('p', 'notice', 'That lecture is no longer here.'));
    if (!lectures.length) root.append(node('p', '', 'Lecture content has not been prepared for this course.'));
    const list = node('ul', 'topic-list');
    for (const item of lectures) {
      const parts = [];
      if (item.notes.length) parts.push(`${item.notes.length} note${item.notes.length === 1 ? '' : 's'}`);
      if (item.highlights.length) parts.push(`${item.highlights.length} highlight${item.highlights.length === 1 ? '' : 's'}`, `${duration(watchTime(item))} of ${duration(item.recording.duration_s)}`);
      const count = parts.join(' · ') || 'No lecture additions';
      const row = topicRow(lectureLink(item), item.title, [date(item.recording.recorded_on), item.summary, node('span', 'small lecture-count', count)]);
      const cover = item.highlights[0]?.thumbnail.asset || item.chapters?.find(chapter => chapter.slide_preview)?.slide_preview;
      if (cover) row.querySelector('a').prepend(previewImage(cover));
      list.append(row);
    }
    if (lectures.length) root.append(list);
    return { root, heading, title: 'Lecture' };
  }
  const heading = studyText('h1', '', lecture.title), header = node('div', 'unit-header');
  header.append(node('p', 'eyebrow', date(lecture.recording.recorded_on)), heading, studyText('p', 'unit-summary', lecture.summary));
  // The Study topics that teach this lecture, so highlights and lessons lead to each other.
  const taught = data.units.filter(unit => (unit.lectures || []).includes(lecture.key));
  if (taught.length) {
    const line = append(node('p', 'small related-work'), node('span', 'related-label', 'Study: '));
    taught.forEach((unit, index) => { if (index) line.append(', '); const link = studyText('a', '', unit.title); link.href = `#study/${unit.key}/content`; line.append(link); });
    header.append(line);
  }
  root.append(header);
  const active = decode(highlightKey), chapters = lecture.chapters || [];
  if (highlightKey && ![...lecture.notes, ...lecture.highlights, ...chapters].some(item => item.key === active)) root.append(node('p', 'notice', 'That lecture passage is no longer here.'));
  if (chapters.length) {
    root.append(...lectureChapters(lecture, chapters, active));
  } else {
    root.append(...gaps(lecture).map(gap => gap.row));
  }
  if (!chapters.length && lecture.notes.length) {
    const notes = append(node('section', 'lecture-notes read-section'), node('h2', '', 'Notes'));
    notes.append(append(node('ul', 'lecture-note-list'), ...lecture.notes.map(note => noteView(note, note.key === active))));
    root.append(notes);
  }
  if (!chapters.length && lecture.highlights.length) {
    const highlights = append(node('section', 'lecture-highlights read-section'), node('h2', '', 'Highlights'));
    for (const highlight of lecture.highlights) highlights.append(highlightView(highlight, highlight.key === active));
    root.append(highlights);
  }
  if (!chapters.length && !lecture.notes.length && !lecture.highlights.length) root.append(node('p', 'small', 'No notes or highlights for this lecture.'));
  // The list shows the newest first; Next follows the course, from one lecture to the one after it.
  const following = lectures[lectures.indexOf(lecture) - 1];
  if (following) root.append(nextStep({ href: lectureLink(following), title: following.title, detail: date(following.recording.recorded_on) }));
  const comments = renderCommentedView(lecture, 'lectures', root);
  return { root: comments.root, heading, title: lecture.title, current: lecture.key, lecture };
}
