"""E2E timing test for the RAG pipeline."""
import requests, time, sys, json

BASE = 'http://localhost:8002/api/v1'
DOC  = r'D:\RAQ-Document-summarizer\testing-docs\2-RFP 2025-06.pdf'

t0 = time.time()

def ts():
    return f'+{time.time()-t0:6.1f}s'

print('=== E2E TEST: 2-RFP 2025-06.pdf ===')
print()

# ── 1. Upload ──────────────────────────────────────────────────────────────────
print(f'[{ts()}] UPLOADING document...')
with open(DOC, 'rb') as f:
    r = requests.post(
        f'{BASE}/documents/upload/',
        files={'file': ('2-RFP_2025-06.pdf', f, 'application/pdf')},
        data={
            'tender_reference': 'TEST-E2E-RFP-2025',
            'tender_title': 'E2E Test — RFP 2025-06',
        },
        timeout=60,
    )
if r.status_code not in (200, 201, 202):
    print('Upload FAILED:', r.status_code, r.text[:500])
    sys.exit(1)

doc    = r.json()
doc_id = doc.get('id') or doc.get('document_id')
print(f'[{ts()}] Uploaded  doc_id={doc_id}  status={r.status_code}')
print()

# ── 2. Kick processing ─────────────────────────────────────────────────────────
print(f'[{ts()}] KICKING processing pipeline...')
r2 = requests.post(f'{BASE}/documents/{doc_id}/process/', timeout=30)
print(f'[{ts()}] Kick: {r2.status_code}  {r2.text[:200]}')
print()

# ── 3. Poll until done ─────────────────────────────────────────────────────────
print(f'[{ts()}] POLLING every 4s  (timeout 10 min)...')
print('-' * 70)

stage_log   = []   # (wall_time, stage)
stage_times = {}   # stage -> first-seen wall_time
last_stage  = None
poll_start  = time.time()

while True:
    try:
        r3   = requests.get(f'{BASE}/documents/{doc_id}/summary/status/', timeout=15)
        data = r3.json()
    except Exception as exc:
        print(f'[{ts()}] poll error: {exc}')
        time.sleep(4)
        continue

    doc_status = data.get('document_status', '?')
    sum_status = data.get('summary_status')
    stage      = data.get('progress_stage') or doc_status

    if stage != last_stage:
        wall = time.time() - t0
        stage_log.append((wall, stage))
        stage_times[stage] = wall
        print(f'[+{wall:6.1f}s]  {stage:<35}  doc={doc_status}  sum={sum_status}')
        last_stage = stage

    if sum_status in ('completed', 'failed') or doc_status == 'failed':
        total = time.time() - t0
        print('-' * 70)
        print(f'[+{total:6.1f}s]  DONE  doc={doc_status}  sum={sum_status}')
        if data.get('error_message'):
            print(f'  error_message: {data["error_message"]}')
        break

    if time.time() - poll_start > 600:
        print('TIMEOUT: exceeded 10 minutes')
        break

    time.sleep(4)

# ── 4. Stage timing breakdown ──────────────────────────────────────────────────
print()
print('=== STAGE TIMING BREAKDOWN ===')
for i, (wall, stage) in enumerate(stage_log):
    if i + 1 < len(stage_log):
        dur = stage_log[i+1][0] - wall
        print(f'  {wall:6.1f}s  {stage:<40}  duration: {dur:.1f}s')
    else:
        print(f'  {wall:6.1f}s  {stage:<40}  (terminal)')
print()

# ── 5. Fetch & inspect summary ─────────────────────────────────────────────────
print(f'[{ts()}] Fetching summary...')
r4 = requests.get(f'{BASE}/documents/{doc_id}/summary/', timeout=15)
if r4.status_code == 200:
    sdata = r4.json()
    sj    = sdata.get('summary_json', {})
    print(f'  total_tokens: {sdata.get("total_tokens")}')
    print(f'  version:      {sdata.get("version")}')
    print()
    print('--- Summary sections ---')
    for section, val in sj.items():
        if section.startswith('_'):
            continue
        if isinstance(val, dict):
            text = val.get('text') or val.get('item') or ''
            srcs = val.get('sources', [])
            print(f'\n  [{section}]  ({len(srcs)} sources)')
            print(f'    {str(text)[:300]}')
        elif isinstance(val, list):
            print(f'\n  [{section}]  {len(val)} items')
            for item in val[:2]:
                if isinstance(item, dict):
                    text = item.get('text') or item.get('item') or item.get('signal') or item.get('insight') or ''
                    srcs = item.get('sources', [])
                    print(f'    • {str(text)[:200]}  (srcs={len(srcs)})')
else:
    print(f'  Summary GET: {r4.status_code}  {r4.text[:400]}')

# ── 6. Fetch & inspect insights ───────────────────────────────────────────────
print()
r5 = requests.get(f'{BASE}/documents/{doc_id}/insights/', timeout=15)
if r5.status_code == 200:
    insights = r5.json()
    print(f'=== EXTRACTED INSIGHTS ({len(insights)} types) ===')
    for ins in insights:
        items = ins.get('payload', {}).get('items', [])
        print(f'\n  [{ins["extraction_type"]}]  items={ins["item_count"]}  conf={ins["confidence_score"]:.2f}  tokens={ins.get("token_usage",{}).get("total_tokens","?")}')
        for item in items[:2]:
            req  = item.get('requirement') or item.get('insight') or ''
            page = item.get('page', '?')
            conf = item.get('confidence', '?')
            cite = item.get('citation_verified', '?')
            print(f'    p{page}  conf={conf}  cited={cite}  -> {str(req)[:160]}')
else:
    print(f'  Insights GET: {r5.status_code}')

# ── 7. Save raw output for reference ──────────────────────────────────────────
out = {
    'document_id': doc_id,
    'summary': r4.json() if r4.status_code == 200 else None,
    'insights': r5.json() if r5.status_code == 200 else None,
    'stage_log': stage_log,
    'total_wall_seconds': time.time() - t0,
}
with open(r'D:\RAQ-Document-summarizer\testing-docs\e2e_result.json', 'w') as fout:
    json.dump(out, fout, indent=2, default=str)

print()
print(f'Total wall time: {time.time()-t0:.1f}s')
print('Raw output saved to testing-docs/e2e_result.json')
print('=== TEST COMPLETE ===')
