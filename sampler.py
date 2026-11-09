#!/usr/bin/python3 -I
# Task-manager sampler: every 2 s reads /proc, keeps 1 h of history in memory and writes
# /run/taskmgr/state.json = {"s": snapshot, "h": {"2"|"10"|"60": encoded history}} for handler.ts.
# History encoding per series: [scale, "base64url string"], value ≈ idx(char)/63*scale.
import os, json, time, collections
OUT = '/run/taskmgr/state.json'
A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
STEP = 2
RANGES = {'2': (120, 60), '10': (600, 120), '60': (3600, 120)}  # minutes → (seconds, points)
hist = collections.deque(maxlen=3600 // STEP)  # (ts, cpu%, mem%, disk KB/s, net KB/s)

def rd(p):
    try:
        with open(p) as f: return f.read()
    except OSError: return ''

def iface():
    for l in rd('/proc/net/route').splitlines()[1:]:
        f = l.split('\t')
        if len(f) > 1 and f[1] == '00000000': return f[0]
    return 'eth0'

def disk():
    for l in rd('/proc/diskstats').splitlines():
        f = l.split()
        n = f[2] if len(f) > 9 else ''
        if (n[:2] in ('vd', 'sd') and not n[-1].isdigit()) or (n.startswith('nvme') and 'p' not in n[4:]):
            return int(f[5]), int(f[9])
    return 0, 0

def sample():
    c = [int(x) for x in rd('/proc/stat').split('\n')[0].split()[1:]]
    procs = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit(): continue
        s = rd(f'/proc/{pid}/stat')
        if not s: continue
        name = s[s.find('(') + 1:s.rfind(')')]
        f = s[s.rfind(')') + 2:].split(' ')
        st = rd(f'/proc/{pid}/statm').split()
        rss = int(st[1]) * 4 if len(st) > 1 else 0
        if f[0] == 'Z' or (rss == 0 and f[0] != 'R'): continue
        if name == 'MainThread':
            name = rd(f'/proc/{pid}/cmdline').split('\0')[0].rsplit('/', 1)[-1] or name
        procs[pid] = (name, int(f[11]) + int(f[12]), rss)
    nl, i = rd('/proc/net/dev'), iface()
    rx = tx = 0
    for l in nl.splitlines():
        if l.strip().startswith(i + ':'):
            v = l.split(':', 1)[1].split(); rx, tx = int(v[0]), int(v[8])
    rs, ws = disk()
    return dict(at=time.time(), total=sum(c), idle=c[3] + (c[4] if len(c) > 4 else 0), procs=procs, rx=rx, tx=tx, rs=rs, ws=ws)

def enc(vals, scale=None):
    sc = scale or max(8, max(vals or [0]) * 1.15)
    return [round(sc, 1), ''.join(A[max(0, min(63, round(v / sc * 63)))] for v in vals)]

def history(key):
    secs, pts = RANGES[key]
    now, b = time.time(), secs / pts
    out = [[] for _ in range(4)]
    buckets = [[] for _ in range(pts)]
    for h in hist:
        k = int((h[0] - (now - secs)) // b)
        if 0 <= k < pts: buckets[k].append(h)
    first = next((k for k, x in enumerate(buckets) if x), pts)
    for k in range(first, pts):
        x = buckets[k] or buckets[k - 1] if k else buckets[k]
        buckets[k] = x
        for j in range(4): out[j].append(sum(e[j + 1] for e in x) / len(x) if x else 0)
    return [enc(out[0], 100), enc(out[1], 100), enc(out[2]), enc(out[3])]

r1 = lambda x: round(x * 10) / 10
ncpu = sum(1 for l in rd('/proc/stat').splitlines() if l[:3] == 'cpu' and l[3:4].isdigit())
prev = sample()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
while True:
    time.sleep(STEP)
    cur = sample()
    dt, dtot = max(cur['at'] - prev['at'], .1), max(cur['total'] - prev['total'], 1)
    mi = {l.split(':')[0]: int(l.split()[1]) for l in rd('/proc/meminfo').splitlines() if len(l.split()) > 1}
    mb = lambda kb: round(kb / 1024)
    sv = os.statvfs('/')
    g = {}
    for pid, (name, ticks, rss) in cur['procs'].items():
        x = g.setdefault(name, [0, 0.0, 0.0])
        x[0] += 1; x[1] += max(ticks - prev['procs'].get(pid, (0, ticks))[1], 0) / dtot * 100; x[2] += rss / 1024
    p = sorted(([n[:18], c, r1(cp), round(m)] for n, (c, cp, m) in g.items()), key=lambda r: (-r[2], -r[3]))[:10]
    cpu = r1(100 * (1 - (cur['idle'] - prev['idle']) / dtot))
    used = mi['MemTotal'] - mi['MemAvailable']
    dr, dw = round((cur['rs'] - prev['rs']) * .5 / dt), round((cur['ws'] - prev['ws']) * .5 / dt)
    nr, nt = round((cur['rx'] - prev['rx']) / 1024 / dt), round((cur['tx'] - prev['tx']) / 1024 / dt)
    hist.append((cur['at'], cpu, used / mi['MemTotal'] * 100, dr + dw, nr + nt))
    snap = dict(c=cpu, k=ncpu, m=[mb(used), mb(mi['MemTotal'])], s=[mb(mi['SwapTotal'] - mi['SwapFree']), mb(mi['SwapTotal'])],
                d=[r1((sv.f_blocks - sv.f_bfree) * sv.f_frsize / 2**30), r1(sv.f_blocks * sv.f_frsize / 2**30), dr, dw],
                n=[nr, nt], l=' '.join(rd('/proc/loadavg').split()[:3]), u=int(float(rd('/proc/uptime').split()[0])),
                t=len(cur['procs']), p=p)
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f: json.dump(dict(s=snap, h={k: history(k) for k in RANGES}), f, separators=(',', ':'), ensure_ascii=False)
    os.replace(tmp, OUT)
    prev = cur
