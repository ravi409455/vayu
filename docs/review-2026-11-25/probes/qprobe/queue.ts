// Does the upload queue start the 3rd, 4th... file after the first two finish?
let n = 0;
(globalThis as any).document = { cookie: "" };
globalThis.fetch = (async (url: string) => {
  await new Promise((r) => setTimeout(r, 30));
  return new Response(JSON.stringify({ id: `asset-${++n}`, status: "verified", part_size: 8 }), { status: 200, headers: { "Content-Type": "application/json" } });
}) as any;
const m = await import("/Users/ravi/DevSpace/inspex/web/src/lib/uploadManager.ts");
await Promise.all([1, 2, 3, 4, 5].map((i) => m.addFile({ bookingId: "b", fieldKey: "f", kind: "file", file: new Blob([`x${i}`]), name: `f${i}`, source: "gallery" })));
await new Promise((r) => setTimeout(r, 1000));
const states: string[] = [];
for (let i = 1; i <= n; i++) { const u = m.uploadFor(`asset-${i}`); if (u) states.push(`${u.assetId}:${u.status}`); }
console.log("after 1 s:", states.join(" "));
