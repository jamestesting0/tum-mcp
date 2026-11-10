export const katexGroups = '.katex-html > .katex-base';

export function mathSizeFloor(element, rem) {
  // Graphs already keep their smallest label at 12px when the drawing has to scale.
  if (element.closest('foreignObject')) return .75 * rem;
  if (element.closest('td, th')) return .875 * rem;
  return rem;
}

function fit(elements) {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const rows = elements.filter(element => element.isConnected).map(element => {
    const expression = element.localName === 'study-inline-math' ? element.firstElementChild : element;
    expression.style.fontSize = '';
    return { element, expression };
  });
  const sizes = rows.map(({ element, expression }) => {
    const style = getComputedStyle(element);
    const width = element.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    if (width <= 0) return '';
    const groups = [...expression.querySelectorAll(katexGroups)];
    const ink = groups[0] || (expression.matches('math') ? expression : expression.querySelector('math'));
    if (!ink) return '';
    const widest = groups.length
      ? Math.max(...groups.map(group => group.getBoundingClientRect().width))
      : ink.getBoundingClientRect().width;
    const size = parseFloat(getComputedStyle(expression).fontSize);
    const rendered = parseFloat(getComputedStyle(ink).fontSize);
    const minimum = mathSizeFloor(element, rem) * size / rendered;
    const fitted = widest > width ? size * (width - .5) / widest : size;
    const target = Math.max(minimum, fitted);
    return target === size ? '' : `${target}px`;
  });
  rows.forEach(({ expression }, index) => { expression.style.fontSize = sizes[index]; });
}

const fitter = new ResizeObserver(entries => fit(entries.map(entry => entry.target)));
export function fitMath(element) {
  fitter.observe(element);
  document.fonts.ready.then(() => fit([element]));
}

customElements.define('study-inline-math', class extends HTMLElement {
  connectedCallback() { fitMath(this); }
  disconnectedCallback() { fitter.unobserve(this); }
});
