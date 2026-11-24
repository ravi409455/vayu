import { readFileSync } from "fs";
import { evaluateTree, missingFields, pageGaps } from "/Users/ravi/DevSpace/inspex/web/src/lib/formSpec";
const d = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
const tree = d.form;
const t0 = performance.now(); for (let i = 0; i < 50; i++) evaluateTree("inspection", tree, {}, {}); const one = (performance.now() - t0) / 50;
// what the Wizard does per render: missingOn twice per step (rail + select), lockedFrom, gaps (x3 parts), FormRenderer, checkin
const steps = tree.pages.length + 1;
const t1 = performance.now(); for (let r = 0; r < 10; r++) { for (let k = 0; k < 2 * steps + steps; k++) { pageGaps("inspection", tree, tree.pages[k % tree.pages.length], {}, {}); } missingFields("inspection", tree, {}, {}); evaluateTree("inspection", tree, {}, {}); } const per = (performance.now() - t1) / 10;
console.log(`one evaluateTree: ${one.toFixed(2)} ms; Wizard re-render (~${3 * steps + 2} evaluations): ${per.toFixed(1)} ms`);
