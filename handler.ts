// Task-manager widget: answers from /run/taskmgr/state.json (written every 2 s by taskmgr-sampler.service).
// Query data: "a2" | "a10" | "a60" → snapshot + history for that range (minutes). Answer must fit 1024 chars.
const q = JSON.parse(await Bun.stdin.text())
let st: any
try { st = JSON.parse(await Bun.file('/run/taskmgr/state.json').text()) } catch { console.log(JSON.stringify({ answer: '{"e":"сборщик не запущен"}' })); process.exit(0) }
const key = String(q.data ?? '').slice(1)
const out = { ...st.s, r: key in st.h ? key : '2', h: st.h[key] ?? st.h['2'] }
let a = JSON.stringify(out)
while (a.length > 1024 && out.p.length) { out.p.pop(); a = JSON.stringify(out) }
console.log(JSON.stringify({ answer: a }))
