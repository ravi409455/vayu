/**
 * Words people read (docs/plan-leads-bookings-words.md): experts say "lead", Ops and Admin say
 * "booking", and "job" is never shown. Reads every text in the web app (strings and JSX text, not
 * code names or comments) and fails on a slip.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname);
// a word on its own: not part of a code name (job-row, jobSpan), a path (/jobs) or a value name (job.booking_id)
const JOB = /(?<![\w\-/.:{$])jobs?(?![\w\-/}]|[.:]\w)/i;
const BOOKING = /(?<![\w\-/.:{$])bookings?(?![\w\-/}]|[.:]\w)/i;
const EXPERT_ONLY = ["pages/expert/"];
// the number keeps its name for experts too, and the lead page's detail row says "Booking"
const EXPERT_BOOKING_OK = [/^Booking ID\b/i, /\bBooking ID\b/i];
const EXPERT_LABEL_OK = new Set(["Booking"]);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return files(p);
    return /\.(ts|tsx)$/.test(n) && !/\.test\.|\.d\.ts$/.test(n) ? [p] : [];
  });
}

/** Texts a person can read: string and template parts and JSX text. One-word lowercase strings
 *  are code keys (query keys, store names, class names), so they are left out. */
function texts(path: string): { text: string; line: number; jsx: boolean }[] {
  const src = ts.createSourceFile(
    path,
    readFileSync(path, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    path.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const out: { text: string; line: number; jsx: boolean }[] = [];
  const visit = (n: ts.Node) => {
    if (ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) return;
    const add = (text: string, jsx = false) => {
      const t = text.trim();
      // one lowercase word with nothing around it is a code key; " job" inside a sentence is not
      if (!t || (!/\s/.test(text) && !/^[A-Z]/.test(t))) return;
      out.push({ text: t, line: src.getLineAndCharacterOfPosition(n.getStart()).line + 1, jsx });
    };
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) add(n.text);
    else if (ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) add(n.text);
    else if (ts.isJsxText(n)) add(n.text, true);
    n.forEachChild(visit);
  };
  visit(src);
  return out;
}

function slips(): string[] {
  const out: string[] = [];
  for (const f of files(ROOT)) {
    const rel = relative(ROOT, f);
    const expert = EXPERT_ONLY.some((d) => rel.startsWith(d));
    for (const t of texts(f)) {
      if (JOB.test(t.text)) out.push(`${rel}:${t.line} says "job": ${t.text}`);
      if (expert && BOOKING.test(t.text) && !EXPERT_BOOKING_OK.some((r) => r.test(t.text)) && !(t.jsx && EXPERT_LABEL_OK.has(t.text)))
        out.push(`${rel}:${t.line} says "booking" to an expert: ${t.text}`);
    }
  }
  return out;
}

describe("words people read", () => {
  it("never say job; experts say lead, Ops and Admin say booking", () => {
    expect(slips()).toEqual([]);
  });
});
