/** Where (in pixels, inside the box) the caret of a textarea is: a hidden copy of the text up to the
 *  caret is laid out with the same font, and the end of it is measured. */
export function caretPoint(el: HTMLTextAreaElement, pos: number): { left: number; top: number; line: number } {
  const cs = getComputedStyle(el);
  const mirror = document.createElement("div");
  for (const p of ["fontFamily", "fontSize", "fontWeight", "letterSpacing", "lineHeight", "paddingTop", "paddingLeft", "paddingRight", "paddingBottom", "borderTopWidth", "borderLeftWidth", "tabSize"] as const) {
    (mirror.style as unknown as Record<string, string>)[p] = cs[p];
  }
  mirror.style.cssText += ";position:absolute;visibility:hidden;white-space:pre;top:0;left:0;box-sizing:border-box;";
  mirror.textContent = el.value.slice(0, pos);
  const mark = document.createElement("span");
  mark.textContent = "​";
  mirror.appendChild(mark);
  document.body.appendChild(mirror);
  const line = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4 || 18;
  const out = { left: mark.offsetLeft - el.scrollLeft, top: mark.offsetTop - el.scrollTop, line };
  document.body.removeChild(mirror);
  return out;
}
