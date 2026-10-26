// Only the local compiler's inert MathML is accepted; prose never becomes HTML.
const namespace = 'http://www.w3.org/1998/Math/MathML';
const allowed = new Set('math mrow mi mn mo mtext mfrac msqrt mroot msub msup msubsup mtable mtr mtd munder mover munderover mmultiscripts mprescripts none mspace mstyle menclose'.split(' '));
const attributes = new Set('display mathvariant displaystyle stretchy linethickness fence separator accent accentunder notation columnalign rowalign columnspacing rowspacing columnlines rowlines scriptlevel width height depth lspace rspace minsize maxsize'.split(' '));
export function parseMath(value) {
  const parsed = new DOMParser().parseFromString(value, 'application/xml');
  if (parsed.documentElement.localName !== 'math' || parsed.querySelector('parsererror') || ![...parsed.querySelectorAll('*')].every(element =>
    element.namespaceURI === namespace && allowed.has(element.localName) &&
    [...element.attributes].every(attribute => attributes.has(attribute.name) || attribute.name === 'xmlns'))) return null;
  return document.importNode(parsed.documentElement, true);
}
