export function h(tag, props = {}, ...children) {
  const [name, ...classes] = tag.split('.');
  const element = document.createElement(name || 'div');
  if (classes.length) element.className = classes.join(' ');
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === 'class') element.className = [element.className, value].filter(Boolean).join(' ');
    else if (key === 'text') element.textContent = value;
    else if (key === 'html') element.innerHTML = value;
    else if (key.startsWith('on')) element.addEventListener(key.slice(2), value);
    else if (key === 'style') for (const [name, setting] of Object.entries(value)) element.style.setProperty(name.startsWith('--') ? name : name.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`), String(setting));
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else element.setAttribute(key, value === true ? '' : value);
  }
  element.append(...children.flat().filter(child => child != null && child !== false));
  return element;
}

export function replace(element, ...children) {
  element.replaceChildren(...children.flat().filter(child => child != null && child !== false));
  return element;
}

export const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));

export const slice = (text, fraction) => text.slice(0, Math.round(text.length * clamp(fraction)));
