import { node, studyText, button, append, announce, confirmAction, focusHeading } from './dom.mjs';
import { renderReading } from './reading.mjs';
import { renderResponse } from './exercise-response.mjs';
import { annotateExam } from './anchors.mjs';
import { exam, patterns, quietLink } from './exam-state.mjs';

const plain = text => studyText('span', '', text || '').textContent;
const clock = ms => { const total = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`; };

// A paper is either a forecast practice exam or a replayed past variant, in one shape.
export function paperFor(kind, key) {
  if (kind === 'mock') {
    const mock = exam.mocks.find(item => item.key === key);
    return mock && { kind, key, revision: mock.revision, title: plain(mock.title), minutes: mock.duration_minutes, instructions: mock.instructions,
      forecast: true, questions: mock.questions, item: `mock:${mock.key}` };
  }
  for (const sitting of exam.sittings) for (const variant of sitting.variants) if (variant.key === key && variant.replayable) {
    const label = sitting.variants.length > 1 ? `${plain(sitting.label)} · ${plain(variant.label)}` : plain(sitting.label);
    return { kind: 'paper', key, revision: variant.revision, title: label, minutes: exam.profile?.duration_minutes || null,
      instructions: '', forecast: false, questions: variant.questions, sitting };
  }
  return null;
}
const questionItem = (paper, question) => paper.kind === 'mock' ? paper.item : `question:${question.key}`;

export function renderExamMode(paper, store) {
  const attempt = store.attempt(paper.kind, paper.key, paper.revision), state = attempt.value;
  const root = node('div', 'exam-mode'), heading = node('h1', '', paper.title);
  const header = append(node('div', 'unit-header'), node('p', 'eyebrow', paper.forecast ? 'Practice exam' : 'Past exam'), heading);
  root.append(header);
  const total = paper.questions.reduce((sum, question) => sum + (question.points || 0), 0);
  const facts = [paper.minutes && `${paper.minutes} minutes`, total && `${total} points`, exam.profile?.allowed_aids].filter(Boolean);
  if (facts.length) header.append(studyText('p', 'small', facts.join(' · ')));
  if (paper.forecast) header.append(node('p', 'notice', 'AI-written practice exam built from past patterns and course material. It is not a past or leaked exam, and topics can differ in the real exam.'));
  const body = node('div'); root.append(body);
  let timer = 0, focusAfterPaint = null;
  // A reopened page resumes paused: the last checkpoint holds the time used.
  if (state.running) { state.running = null; attempt.save(); }
  const elapsed = () => state.elapsed + (state.running ? Date.now() - state.running : 0);
  function pause() { if (state.running) { state.elapsed = elapsed(); state.running = null; attempt.save(); } }
  function stopTicking() { clearInterval(timer); timer = 0; }
  function start(timed) {
    state.started = true; state.timed = timed; state.running = timed ? Date.now() : null; attempt.save(); paint();
  }
  function paint() {
    stopTicking(); if (state.finished) results(); else if (state.started) running(); else intro();
    if (focusAfterPaint) { document.getElementById(focusAfterPaint)?.focus({ preventScroll: true }); focusAfterPaint = null; }
  }
  function intro() {
    const stack = node('div', 'stack');
    if (paper.instructions) stack.append(studyText('p', '', paper.instructions));
    stack.append(node('p', 'small', 'Work on paper or in the answer fields. Hints and solutions stay hidden until you finish.'));
    const timedChoice = node('label', 'exam-timed'), box = node('input'); box.type = 'checkbox'; box.checked = Boolean(paper.minutes);
    timedChoice.append(box, node('span', '', paper.minutes ? `Use a ${paper.minutes}-minute timer` : 'Show elapsed time'));
    stack.append(timedChoice, button('Start', () => start(box.checked), 'primary'));
    body.replaceChildren(stack);
  }
  function timerBar() {
    const bar = node('div', 'exam-timer'); bar.setAttribute('role', 'timer');
    const readout = node('span', 'exam-clock'), toggle = button('', () => {
      if (state.running) pause(); else { state.running = Date.now(); attempt.save(); }
      tick(); toggle.textContent = state.running ? 'Pause' : 'Resume';
    }, 'quiet');
    toggle.textContent = state.running ? 'Pause' : 'Resume';
    let warned = false, beats = 0;
    function tick() {
      if (!readout.isConnected && timer) { pause(); stopTicking(); return; }
      const used = elapsed();
      if (state.running && ++beats % 5 === 0) { state.elapsed = used; state.running = Date.now(); attempt.save(); }
      if (paper.minutes) {
        const left = paper.minutes * 60000 - used;
        readout.textContent = left >= 0 ? `${clock(left)} left` : `Time is up · ${clock(-left)} over`;
        if (left < 0 && !warned) { warned = true; announce('Time is up. Finish when you are ready.'); }
      } else readout.textContent = `${clock(used)} elapsed`;
    }
    tick(); timer = setInterval(tick, 1000);
    bar.append(readout, toggle);
    return bar;
  }
  function running() {
    const parts = [];
    if (state.timed) parts.push(timerBar());
    paper.questions.forEach(question => {
      const section = node('section', 'exam-section exam-question'); section.dataset.question = question.key;
      const title = `Question ${question.number}${question.points ? ` · ${question.points} points` : ''}`;
      section.append(node('h2', '', title));
      const statement = renderReading({ blocks: question.statement });
      for (const [i, element] of [...statement.querySelectorAll('.reading-material')].entries()) annotateExam(element, questionItem(paper, question), paper.revision, `${question.key}:statement:${i}`);
      section.append(statement);
      if (question.parts?.length) section.append(append(node('ol', 'exam-parts'), ...question.parts.map(text => studyText('li', '', text))));
      const response = renderResponse(question.check, state.answers[question.key] || '', value => { state.answers[question.key] = value.slice(0, 64000); attempt.save(); }, `${paper.key}-${question.key}`);
      if (!question.check) {
        const field = node('label', 'stack exam-free', 'Your answer (optional)'), area = node('textarea'); area.rows = 4; area.maxLength = 64000;
        area.value = state.answers[question.key] || ''; area.addEventListener('input', () => { state.answers[question.key] = area.value; attempt.save(); });
        field.append(area); section.append(field);
      } else section.append(response.root);
      parts.push(section);
    });
    const finish = button('Finish and see results', () => confirmAction({
      title: 'Finish this exam?', message: 'You will see solutions and score your answers. You can retake it later.', action: 'Finish', trigger: finish,
      onConfirm() { pause(); state.finished = true; attempt.save(); paint(); window.scrollTo({ top: 0 }); focusHeading(heading); },
    }), 'primary');
    body.replaceChildren(...parts, append(node('div', 'cluster exam-finish'), finish));
  }
  function results() {
    let earned = 0, possible = 0;
    const perPattern = new Map(), sections = [];
    for (const question of paper.questions) {
      const marks = (state.marks[question.key] ||= {});
      const section = node('section', 'exam-section exam-result'); section.dataset.question = question.key;
      section.append(node('h2', '', `Question ${question.number}`));
      section.append(renderReading({ blocks: question.statement }));
      const answer = state.answers[question.key];
      let correct = null;
      if (question.check?.kind === 'self_check') {
        if (answer) section.append(append(node('div', 'exam-your-answer'), node('p', 'small', 'Your answer'), append(node('pre'), node('code', '', answer))));
        section.append(append(node('div', 'exam-compare'), node('p', 'small', 'Compare with'), studyText('p', '', question.check.model_answer),
          append(node('ul'), ...question.check.rubric.map(text => studyText('li', '', text)))));
      } else if (question.check) {
        const response = renderResponse(question.check, answer || '', () => {}, `${paper.key}-${question.key}-review`);
        const result = response.validate(); correct = result.valid && result.correct;
        response.root.inert = true; response.showResult(true);
        section.append(node('p', `small exam-check ${correct ? 'right' : 'wrong'}`, correct ? 'Your answer matches.' : result.valid ? 'Your answer does not match.' : 'No answer given.'), response.root);
      } else if (answer) section.append(append(node('div', 'exam-your-answer'), node('p', 'small', 'Your answer'), append(node('pre'), node('code', '', answer))));
      const solution = node('details', 'disclosure'); solution.open = true;
      solution.append(node('summary', '', question.solution.origin === 'official' ? 'Official solution' : 'Prepared solution, not official'), renderReading({ blocks: question.solution.blocks }));
      section.append(solution);
      let score = 0, max = 0;
      if (question.marking?.length) {
        const list = node('fieldset', 'exam-marking'); list.append(node('legend', 'small', question.marking_basis === 'official' ? 'Official marking' : 'Score your answer'));
        question.marking.forEach((criterion, index) => {
          const row = node('label', 'option'), box = node('input'); box.type = 'checkbox'; box.id = `mark-${paper.key}-${question.key}-${index}`;
          max += criterion.points;
          if (criterion.auto) { box.checked = correct === true; box.disabled = true; }
          else { box.checked = marks[index] === true; box.addEventListener('change', () => { marks[index] = box.checked; attempt.save(); focusAfterPaint = box.id; paint(); }); }
          if (box.checked) score += criterion.points;
          row.append(box, studyText('span', 'option-body', `${criterion.text} (${criterion.points})${criterion.auto ? ' · checked automatically' : ''}`));
          list.append(row);
        });
        section.append(list, node('p', 'small', `${score} of ${max} points`));
        earned += score; possible += max;
      } else {
        const options = node('fieldset', 'exam-marking'); options.append(node('legend', 'small', 'How did it go?'));
        for (const [value, label] of [['full', 'Solved'], ['partial', 'Partly'], ['missed', 'Missed']]) {
          const row = node('label', 'option'), input = node('input'); input.type = 'radio'; input.name = `self-${question.key}`; input.checked = marks.self === value;
          input.id = `self-${paper.key}-${question.key}-${value}`;
          input.addEventListener('change', () => { marks.self = value; attempt.save(); focusAfterPaint = input.id; paint(); });
          row.append(input, node('span', 'option-body', label)); options.append(row);
        }
        section.append(options);
      }
      for (const key of question.patterns || []) {
        const entry = perPattern.get(key) || { score: 0, max: 0, missed: 0 };
        entry.score += score; entry.max += max; entry.missed += marks.self === 'missed' || (max && score < max) ? 1 : 0; perPattern.set(key, entry);
      }
      sections.push(section);
    }
    const summary = node('section', 'exam-section exam-summary'); summary.append(node('h2', '', 'Results'));
    if (possible) summary.append(node('p', 'exam-score', `${earned} of ${possible} points`), node('p', 'small', 'Self-assessed except for automatically checked answers.'));
    if (state.timed) summary.append(node('p', 'small', `Time used: ${clock(state.elapsed)}`));
    const weak = [...perPattern].filter(([, entry]) => entry.missed).map(([key]) => patterns.get(key)).filter(Boolean);
    if (weak.length) {
      const links = node('ul');
      for (const pattern of weak) links.append(append(node('li'), quietLink(plain(pattern.title), `#exam/patterns/${pattern.key}`)));
      summary.append(node('p', '', 'Revisit these patterns:'), links);
    }
    const retake = button('Retake', () => confirmAction({ title: 'Retake this exam?', message: 'Your answers and scores for this attempt are cleared.', action: 'Retake', trigger: retake,
      onConfirm() { attempt.clear(); Object.assign(state, { answers: {}, marks: {}, started: false, finished: false, timed: false, elapsed: 0, running: null }); paint(); } }), 'secondary');
    summary.append(retake);
    body.replaceChildren(summary, ...sections);
  }
  paint();
  return { root, heading, title: paper.title, items: paper.kind === 'mock' ? [paper.item] : paper.questions.map(question => `question:${question.key}`), stop: () => { pause(); stopTicking(); } };
}

export function paperSummary(paper, store) {
  const state = store.attempt(paper.kind, paper.key, paper.revision).value;
  return state.finished ? 'Finished' : state.started ? 'In progress' : 'Not started';
}
