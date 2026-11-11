import { POINTER } from '../app/guide.js';
import { clamp, h } from '../ui/dom.js';
import { stroke } from '../ui/icons.js';

// The Chrome window `tum-mcp login` opens (Playwright starts it, so Chrome says it is being
// controlled by automated software): TUM-Moodle's front page, then TUM's sign-in page,
// recreated from the public pages with a made-up account (go42tum is the page's own example).
// `update(p)` takes the window's progress from 0 to 1, so the same moment always looks the same.

const TUM_LOGO = '<svg viewBox="0 0 740 390" aria-hidden="true"><path fill="#0065BD" d="M405 0h-35v320h-80V0H0v70h70v320h70V70h80v320h220V70h80v320h70V70h80v320h70V0Z"/></svg>';
const USERNAME = 'go42tum';
const PASSWORD_LENGTH = 11;

// Moments of the window's life, as fractions of its time on screen (8.2 s).
const FIRST_LOAD = [0, 0.06];
const TO_LOGIN = 0.25;
const LOGIN_LOAD = [0.226, 0.262];
const TYPE_USER = [0.366, 0.476];
const TYPE_PASSWORD = [0.537, 0.646];
const SENT = 0.738;
const CLOSE = 0.951;
const PRESS = 0.02;
const PATH = [
  { at: 0.11, target: 'start' },
  { at: 0.207, target: 'tum' },
  { at: 0.27, target: 'tum' },
  { at: 0.341, target: 'user' },
  { at: 0.476, target: 'user' },
  { at: 0.512, target: 'password' },
  { at: 0.646, target: 'password' },
  { at: 0.72, target: 'login' },
];
const PRESSES = [{ at: 0.22, target: 'tum' }, { at: 0.348, target: 'user' }, { at: 0.518, target: 'password' }, { at: 0.732, target: 'login' }];

const easeInOut = x => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);
const easeOut = x => 1 - (1 - x) ** 3;
const within = (p, [from, to]) => clamp((p - from) / (to - from));

function moodlePage() {
  return h('div.sg-page.sg-moodle', {},
    h('header.mo-nav', {},
      h('nav.mo-tabs', {}, h('span.mo-tab.is-active', { text: 'Home' }), h('span.mo-tab', { text: 'Help' })),
      h('div.mo-right', {}, h('span.mo-lang', { text: 'English (en)' }), h('span.mo-sep'), h('span.mo-signin', { text: 'Log in' }))),
    h('div.mo-body', {},
      h('div.mo-head', {},
        h('div', {}, h('span.mo-crumb', { text: 'Lernplattform Moodle' }), h('span.mo-crumb', { text: 'Technische Universität München' }), h('h1', { text: 'TUM-Moodle' })),
        h('span.sg-logo', { html: TUM_LOGO })),
      h('section.mo-card', {},
        h('h2', { text: 'TUM-Moodle' }),
        h('p', { text: 'Moodle ist die zentrale Lernplattform der TU München. Moodle bietet Online-Lernräume, in denen Dozierende Materialien und viele unterschiedliche Aktivitäten für Kommunikation, Zusammenarbeit und Selbstlernen bereitstellen. Studierende können die Moodle-Kurse unabhängig von Ort und Zeit und nach eigenen Lernbedürfnissen nutzen.' }),
        h('div.mo-login', {},
          h('strong', { text: 'Login:' }),
          h('div.mo-buttons', {},
            h('span.mo-button.is-primary', { 'data-sg': 'tum', text: 'With TUM ID' }),
            h('span.mo-button', { text: 'With LMU ID' }),
            h('span.mo-button', { text: 'Guests (without ID)' }))))));
}

function field(name, placeholder) {
  return h('div.idp-field', { 'data-sg': name },
    h('span.idp-value'), h('span.idp-caret', { 'aria-hidden': 'true' }), placeholder ? h('span.idp-placeholder', { text: placeholder }) : null);
}

function loginPage() {
  const check = text => h('span.idp-check', {}, h('i'), h('span', { text }), h('sup', { text: text.startsWith('keep') ? '(1)' : '(2)' }));
  return h('div.sg-page.sg-idp', {},
    h('span.sg-logo', { html: TUM_LOGO }),
    h('div.idp-main', {},
      h('h1', { text: 'TUM Login' }),
      h('p', { text: 'Login using your TUM-ID to:' }),
      h('div.idp-service', {}, h('h2', { text: 'TUM Moodle' }), h('p', { text: 'Technical University of Munich, Moodle Learning Management System' }), h('p.idp-muted', { text: 'Website | Privacy Statement' })),
      h('label', { text: 'Username' }), field('user', 'e.g. go42tum / example@tum.de'),
      h('label', { text: 'Password' }), field('password'),
      check('keep me logged in'), check('show data being transmitted'),
      h('div.idp-actions', {}, h('span.idp-button', { 'data-sg': 'login', text: 'LOGIN' }), h('span.idp-or', { text: '- or -' }), h('span.idp-button', { text: 'PASSKEY' })),
      h('span.idp-forgot', { text: 'Forgot your password?' })));
}

export function createSignin() {
  const address = h('span', { text: 'www.moodle.tum.de' });
  const title = h('span.sg-tab-title', { text: 'Home | TUM' });
  const favicon = h('span.sg-favicon', { html: TUM_LOGO });
  const progress = h('i.sg-progress');
  const moodle = moodlePage();
  const login = loginPage();
  const ripple = h('div.sg-ripple');
  const pointerY = h('div.sg-pointer-y', { html: POINTER });
  const pointer = h('div.sg-pointer', {}, pointerY);
  const content = h('div.sg-content', {}, moodle, login, ripple, pointer);
  const element = h('div.signin', { 'aria-hidden': 'true' },
    h('div.sg-tabs', {}, h('span.traffic', {}, h('i'), h('i'), h('i')),
      h('span.sg-tab', {}, favicon, title, h('span.sg-tab-close', { text: '×' })), h('span.sg-newtab', { text: '+' })),
    h('div.sg-toolbar', {},
      h('span.sg-nav', {}, stroke('back', 16), stroke('forward', 16), stroke('reload', 15)),
      h('span.sg-omnibox', {}, stroke('lock', 12), address), h('span.sg-menu', { text: '⋮' }), progress),
    h('div.sg-infobar', {}, h('span.sg-info', { text: 'i' }), h('span', { text: 'Chrome is being controlled by automated test software.' }), h('span.sg-infobar-close', { text: '×' })),
    content);
  const parts = name => content.querySelector(`[data-sg="${name}"]`);
  const user = login.querySelector('[data-sg="user"]');
  const password = login.querySelector('[data-sg="password"]');

  // A control's centre in the content's own (unscaled) coordinates; both pages stay laid out.
  function spot(name) {
    if (name === 'start') return { x: content.offsetWidth * 0.62, y: content.offsetHeight * 0.36 };
    const box = content.getBoundingClientRect();
    const rect = parts(name).getBoundingClientRect();
    const scale = box.width / content.offsetWidth || 1;
    const width = rect.width / scale;
    const inset = name === 'user' || name === 'password' ? Math.min(width / 2, 48) : width / 2;
    return { x: (rect.left - box.left) / scale + inset, y: (rect.top - box.top) / scale + rect.height / scale / 2 };
  }

  function pointAt(p) {
    const from = PATH.findLast(point => p >= point.at) ?? PATH[0];
    const to = p < PATH[0].at ? from : PATH[PATH.indexOf(from) + 1] ?? from;
    const a = spot(from.target);
    const b = spot(to.target);
    const k = to === from ? 1 : clamp((p - from.at) / (to.at - from.at));
    return { x: a.x + (b.x - a.x) * easeInOut(k), y: a.y + (b.y - a.y) * easeOut(k) };
  }

  function update(p) {
    const open = p != null && p < CLOSE;
    element.classList.toggle('is-open', open);
    if (!open) return;
    const onLogin = p >= TO_LOGIN;
    moodle.classList.toggle('is-shown', !onLogin);
    login.classList.toggle('is-shown', onLogin);
    // After LOGIN the sign-in page stays while Moodle loads; the CLI closes the window once Moodle's session is set.
    address.textContent = onLogin ? 'login.tum.de/idp/profile/SAML2/Redirect/SSO' : 'www.moodle.tum.de';
    title.textContent = onLogin ? 'TUM Shibboleth IdP - Login' : 'Home | TUM';
    const loading = p < FIRST_LOAD[1] ? within(p, FIRST_LOAD) : p >= LOGIN_LOAD[0] && p < LOGIN_LOAD[1] ? within(p, LOGIN_LOAD) : p >= SENT ? within(p, [SENT, CLOSE - 0.01]) : 0;
    progress.style.transform = `scaleX(${loading})`;
    progress.style.opacity = loading > 0 && loading < 1 ? '1' : '0';
    element.classList.toggle('is-loading', loading > 0 && loading < 1);
    moodle.classList.toggle('is-blank', p < FIRST_LOAD[1] * 0.7);

    const typedUser = USERNAME.slice(0, Math.round(USERNAME.length * within(p, TYPE_USER)));
    const dots = Math.round(PASSWORD_LENGTH * within(p, TYPE_PASSWORD));
    user.querySelector('.idp-value').textContent = typedUser;
    password.querySelector('.idp-value').textContent = '•'.repeat(dots);
    user.classList.toggle('is-filled', typedUser.length > 0);
    user.classList.toggle('is-focused', p >= 0.348 && p < 0.518);
    password.classList.toggle('is-focused', p >= 0.518 && p < 0.732);

    const { x, y } = pointAt(p);
    pointer.style.transform = `translateX(${x}px)`;
    pointerY.style.transform = `translateY(${y}px)`;
    const press = PRESSES.find(item => p >= item.at && p < item.at + PRESS * 2);
    const k = press ? (p - press.at) / (PRESS * 2) : 1;
    pointer.classList.toggle('is-pressing', Boolean(press) && k < 0.5);
    for (const name of ['tum', 'login']) parts(name).classList.toggle('is-pressed', press?.target === name && k < 0.6);
    ripple.style.opacity = press ? String(1 - k) : '0';
    ripple.style.transform = `translate(${x}px, ${y}px) scale(${0.3 + k * 0.9})`;
    pointer.style.opacity = p < PATH[0].at ? '0' : p > SENT + 0.04 ? String(clamp(1 - (p - SENT - 0.04) / 0.04)) : '1';
  }

  return { element, update };
}
