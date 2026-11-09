// Minimal Bun bot for the widget: /taskmgr sends widget.html, widget queries are answered by handler.ts.
// Only ADMIN_ID can open it or query it — the widget shows your server's processes.
// Run: BOT_TOKEN=... ADMIN_ID=... bun run bot.ts
const TOKEN = process.env.BOT_TOKEN, ADMIN = Number(process.env.ADMIN_ID)
if (!TOKEN || !ADMIN) throw new Error('set BOT_TOKEN and ADMIN_ID')
const dir = import.meta.dir
const html = await Bun.file(`${dir}/widget.html`).text()

async function api(method: string, body: object) {
  const r = await fetch(`https://api.telegram.org/bot${TOKEN}/${method}`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  }).then(r => r.json())
  if (!r.ok) throw new Error(`${method}: ${r.description}`)
  return r.result
}

async function answer(q: any) {
  let data: string | undefined
  if (q.from?.id === ADMIN) {
    const p = Bun.spawn([process.execPath, 'run', `${dir}/handler.ts`], { stdin: new Blob([JSON.stringify({ data: q.data })]) })
    data = JSON.parse((await new Response(p.stdout).text()) || '{}').answer
  }
  await api('answerWidgetQuery', { widget_query_id: q.id, ...(data ? { data } : {}) })
}

let offset = 0
for (;;) {
  try {
    for (const u of await api('getUpdates', { offset, timeout: 50, allowed_updates: ['message', 'widget_query'] })) {
      offset = u.update_id + 1
      const m = u.message
      if (m?.text?.startsWith('/taskmgr') && m.from?.id === ADMIN)
        await api('sendWidget', { chat_id: m.chat.id, html, allow_queries: true, caption: 'Task manager' })
      if (u.widget_query) answer(u.widget_query).catch(console.error)
    }
  } catch (e) { console.error(e); await Bun.sleep(5000) }
}
