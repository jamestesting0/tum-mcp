import data from './data.mjs';
import { node, studyText, append, sourcesNote } from './dom.mjs';
import { renderCommentedView } from './comments.mjs';
import { renderBlockBody } from './reading.mjs';

const lectures = [...(data.lectures?.lectures || [])].sort((a, b) => b.recording.recorded_on.localeCompare(a.recording.recorded_on) || a.key.localeCompare(b.key));
export const lectureLink = (lecture, section) => `#lectures/${encodeURIComponent(lecture.key)}${section ? `/${encodeURIComponent(section.key)}` : ''}`;
function date(value) {
  const day = new Date(value.length === 10 ? value + 'T12:00:00Z' : value);
  return Number.isFinite(day.getTime()) ? new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(day) : 'Date unavailable';
}
export function clock(value) {
  const seconds = Math.floor(value), h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60;
  return `${h ? h + ':' + String(m).padStart(2, '0') : m}:${String(seconds % 60).padStart(2, '0')}`;
}
function timeLink(url, start, end) {
  const link = node('a', 'lecture-time small', `${clock(start)}${end == null ? '' : '–' + clock(end)}`);
  link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  link.setAttribute('aria-label', `Open recording at ${clock(start)}${end == null ? '' : ', through ' + clock(end)}`);
  return link;
}
export function lectureOutline(current = '') {
  const nav = node('nav', 'unit-list'); nav.setAttribute('aria-label', 'Lecture notes');
  for (const lecture of lectures) {
    const link = node('a', 'unit-link'); link.href = lectureLink(lecture);
    link.append(node('span', 'small', date(lecture.recording.recorded_on)), studyText('span', 'unit-title', lecture.title));
    if (lecture.key === current) link.setAttribute('aria-current', 'page');
    nav.append(link);
    if (lecture.key === current) {
      const topics = node('div', 'group-children');
      for (const section of lecture.sections) {
        const topic = studyText('a', 'unit-link', section.title); topic.href = lectureLink(lecture, section); topics.append(topic);
      }
      nav.append(topics);
    }
  }
  return nav;
}
function decode(value) { try { return decodeURIComponent(value || ''); } catch { return ''; } }
function figureView(figure) {
  const root = node('figure', 'lecture-figure'), image = node('img');
  Object.assign(image, { src: figure.asset, alt: figure.alt, width: figure.width, height: figure.height, loading: 'lazy', decoding: 'async' });
  const enlarge = node('a', 'lecture-image'); enlarge.href = figure.asset; enlarge.target = '_blank'; enlarge.rel = 'noopener';
  enlarge.setAttribute('aria-label', `Open full-size image: ${figure.alt}`); enlarge.append(image);
  const fallback = node('p', 'small', 'This image could not load. Open the recording at the time below.'); fallback.hidden = true;
  image.addEventListener('error', () => { enlarge.hidden = true; fallback.hidden = false; });
  const caption = studyText('figcaption', 'small', figure.caption); caption.append(' ', timeLink(figure.url, figure.captured_at_s));
  root.append(enlarge, fallback, caption); return root;
}
export function renderLectures(hash) {
  const [, key, sectionKey] = hash.split('/'), lecture = lectures.find(item => item.key === decode(key));
  const root = node('div', 'lecture-workspace');
  if (!lecture) {
    const heading = node('h1', '', 'Lecture Notes');
    root.append(append(node('div', 'unit-header'), node('p', 'eyebrow', data.course.title), heading));
    if (key) root.append(node('p', 'notice', 'That lecture is no longer here. Choose a prepared lecture below.'));
    if (!lectures.length) root.append(node('p', '', 'Lecture notes have not been prepared for this course.'));
    const list = node('ul', 'topic-list');
    for (const item of lectures) {
      const link = node('a'); link.href = lectureLink(item);
      link.append(studyText('span', 'topic-title', item.title), node('span', 'small', date(item.recording.recorded_on)));
      list.append(append(node('li', 'topic-row'), link));
    }
    root.append(list); return { root, heading, title: 'Lecture Notes' };
  }
  const heading = studyText('h1', '', lecture.title), header = node('div', 'unit-header');
  header.append(node('p', 'eyebrow', date(lecture.recording.recorded_on)), heading, studyText('p', 'unit-summary', lecture.overview));
  const summary = node('section', 'lecture-takeaways');
  summary.append(node('h2', '', 'Keep in mind'), append(node('ul'), ...lecture.takeaways.map(text => studyText('li', '', text))));
  const meta = node('p', 'small lecture-meta', `${lecture.coverage.status === 'complete' ? '' : 'Partial notes · '}Checked ${date(lecture.evidence_as_of)}`);
  if (lecture.coverage.status !== 'complete') {
    const coverage = node('details', 'lecture-coverage small');
    coverage.append(node('summary', '', 'Coverage'));
    const missing = lecture.coverage.missing || [], uncertain = lecture.coverage.uncertain || [];
    coverage.append(node('p', '', 'Some passages are missing or need review.'));
    for (const [label, spans] of [['Missing', missing], ['Unclear speech', uncertain]]) {
      for (const span of spans) coverage.append(node('p', '', `${label}: ${clock(span.start_s)}–${clock(span.end_s)}`));
    }
    header.append(coverage);
  }
  header.append(meta); root.append(header, summary);
  if (sectionKey && !lecture.sections.some(section => section.key === decode(sectionKey))) root.append(node('p', 'notice', 'That section is no longer here. The lecture notes are below.'));
  for (const section of lecture.sections) {
    const topic = node('section', 'read-section lecture-section'); topic.dataset.lectureSection = section.key; topic.dataset.commentTarget = 'lectures';
    if (section.key === decode(sectionKey)) topic.dataset.lectureActiveSection = '';
    const title = studyText('h2', '', section.title), times = node('div', 'cluster lecture-times');
    for (const cite of section.citations) if (cite.key && !section.figures.some(figure => figure.evidence === cite.key)) times.append(timeLink(cite.url, cite.start_s, cite.end_s));
    topic.append(append(node('div', 'section-heading'), title), times);
    for (const block of section.blocks) {
      const material = node('div', 'reading-material lecture-material');
      material.append(append(node('div', 'section-heading'), studyText('h3', '', block.title), sourcesNote(block.sources, data.sources, data.course.synthetic, block.title)), renderBlockBody(block));
      topic.append(material);
    }
    for (const figure of section.figures) topic.append(figureView(figure));
    root.append(topic);
  }
  const comments = renderCommentedView(lecture, 'lectures', root);
  return { root: comments.root, heading, title: lecture.title, current: lecture.key, lecture };
}
