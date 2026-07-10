"""
Synchronous E2E RAG pipeline test with detailed per-stage timing.
Runs:  intake → parsing → chunking → embedding → extraction → summary
All in-process (no Celery needed).
"""
import os, sys, time, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

from apps.documents.models import Document
from apps.intelligence.services.orchestrator import IntelligenceOrchestrator
from apps.intelligence.models import GeneratedSummary, ExtractedInsight
from apps.processing.services.job_service import ProcessingJobService
from apps.processing.services.pipeline_service import DocumentPipelineService

# ─── Find test document ───────────────────────────────────────────────────────
doc = (
    Document.objects
    .filter(original_filename__icontains='2-RFP')
    .order_by('-created_at')
    .first()
)
if not doc:
    print("No '2-RFP' document found. Upload it first.")
    sys.exit(1)

print(f'=== E2E SYNC TEST: {doc.original_filename} ===')
print(f'    doc_id : {doc.id}')
print(f'    status : {doc.status}')
print()

T0         = time.perf_counter()
stage_log  = []

def mark(label):
    t = time.perf_counter() - T0
    stage_log.append((t, label))
    print(f'[+{t:7.2f}s]  {label}')
    return t

mark('test start')

# ─── Step 1: Parse (if not done) ──────────────────────────────────────────────
from apps.parsing.choices import ParsingStatus

def get_parsed(doc):
    doc.refresh_from_db()
    return doc.parsed_document

try:
    parsed = get_parsed(doc)
    if parsed.parsing_status == ParsingStatus.COMPLETED:
        mark(f'parsing already done  pages={parsed.total_pages}  '
             f'chars={len(parsed.structured_text or parsed.raw_text or "")}  '
             f'quality={parsed.parsing_quality_score:.3f}')
    else:
        raise Exception(f'parsing incomplete: {parsed.parsing_status}')
except Exception as initial_exc:
    mark(f'need to parse ({initial_exc})')
    job = ProcessingJobService.get_latest_job_for_document(doc.id)
    if not job:
        job = ProcessingJobService.create_job(doc)

    try:
        t0_intake = time.perf_counter()
        mark('  running intake validation...')
        DocumentPipelineService.run_intake_validation(job)
        mark(f'  intake done  ({time.perf_counter()-t0_intake:.1f}s)')

        t0_parse = time.perf_counter()
        mark('  running document parsing (OCR + sectioning)...')
        DocumentPipelineService.run_document_parsing(job)
        parsed = get_parsed(doc)
        text_src = parsed.structured_text or parsed.raw_text or ''
        mark(f'  parsing done  pages={parsed.total_pages}  chars={len(text_src)}  '
             f'quality={parsed.parsing_quality_score:.3f}  ({time.perf_counter()-t0_parse:.1f}s)')
    except Exception as exc:
        mark(f'PARSE FAILED: {exc}')
        import traceback; traceback.print_exc()
        sys.exit(1)

# ─── Print document stats ─────────────────────────────────────────────────────
text_src = parsed.structured_text or parsed.raw_text or ''
sections_qs = parsed.sections.all()
print()
print('  --- Document stats ---')
print(f'    pages           : {parsed.total_pages}')
print(f'    structured_text : {len(text_src)} chars')
print(f'    sections        : {sections_qs.count()}')
print(f'    quality_score   : {parsed.parsing_quality_score:.3f}')
print(f'    parsing_status  : {parsed.parsing_status}')
print()

# ─── Step 2: Intelligence pipeline ───────────────────────────────────────────
mark('starting intelligence pipeline (chunking→embed→extract→summary)...')
T_intel = time.perf_counter()

try:
    result = IntelligenceOrchestrator.run(str(doc.id), regenerate=True)
    t_intel_done = time.perf_counter() - T_intel
    mark(f'intelligence DONE  wall={t_intel_done:.1f}s  tokens={result.get("total_tokens")}  insights={result.get("insight_count")}')
    run_ok = True
except Exception as exc:
    t_intel_done = time.perf_counter() - T_intel
    mark(f'intelligence FAILED  ({t_intel_done:.1f}s): {exc}')
    import traceback; traceback.print_exc()
    run_ok = False

T_total = time.perf_counter() - T0
print()

# ─── Timing table ─────────────────────────────────────────────────────────────
print('=== STAGE TIMING ===')
for i, (t, label) in enumerate(stage_log):
    dur = (stage_log[i+1][0] - t) if i + 1 < len(stage_log) else (T_total - t)
    bar = '█' * min(int(dur / 2), 40)
    print(f'  {t:7.1f}s  [{dur:5.1f}s] {bar}  {label}')
print(f'\n  TOTAL: {T_total:.1f}s')
print()

if not run_ok:
    sys.exit(1)

# ─── Summary quality ──────────────────────────────────────────────────────────
summary = GeneratedSummary.objects.filter(document=doc, is_current=True).first()
if not summary:
    print('No summary found — pipeline must have failed.')
    sys.exit(1)

sj = summary.summary_json or {}
print(f'=== SUMMARY  (status={summary.status}  tokens={summary.total_tokens}  v{summary.version}) ===')
print()

score = {}
for section, val in sj.items():
    if section.startswith('_'):
        continue
    if isinstance(val, dict):
        text    = val.get('text') or val.get('item') or ''
        sources = val.get('sources', [])
        score[section] = {'items': 1, 'srcs': len(sources), 'chars': len(str(text))}
        status_icon = '✓' if text and sources else ('△' if text else '✗')
        print(f'  {status_icon} [{section}]  srcs={len(sources)}  chars={len(str(text))}')
        if text:
            print(f'      {str(text)[:260]}')
        print()
    elif isinstance(val, list):
        all_srcs = sum(len(i.get('sources', [])) for i in val if isinstance(i, dict))
        score[section] = {'items': len(val), 'srcs': all_srcs}
        status_icon = '✓' if val and all_srcs else ('△' if val else '✗')
        print(f'  {status_icon} [{section}]  {len(val)} items  srcs={all_srcs}')
        for item in val[:2]:
            if isinstance(item, dict):
                text = (item.get('text') or item.get('item') or item.get('signal')
                        or item.get('insight') or item.get('requirement') or '')
                srcs = item.get('sources', [])
                print(f'      • {str(text)[:220]}  [srcs={len(srcs)}]')
        print()

# ─── Extracted insights ───────────────────────────────────────────────────────
insights = list(ExtractedInsight.objects.filter(document=doc, generated_summary=summary))
print(f'=== EXTRACTED INSIGHTS ({len(insights)} types) ===')
total_items = 0
total_cited = 0

for ins in insights:
    items = ins.payload.get('items', [])
    n      = len(items)
    total_items += n
    conf_vals = [i.get('confidence', 0) for i in items if isinstance(i.get('confidence'), (int, float))]
    avg_c  = sum(conf_vals) / len(conf_vals) if conf_vals else 0
    cited  = sum(1 for i in items if i.get('citation_verified'))
    total_cited += cited
    tokens = ins.token_usage.get('total_tokens', '?')
    print(f'\n  [{ins.extraction_type}]  n={n}  avg_conf={avg_c:.2f}  cited={cited}/{n}  tokens={tokens}')
    for item in items[:3]:
        req  = (item.get('requirement') or item.get('insight') or item.get('signal') or '')
        p    = item.get('page', '?')
        c    = item.get('confidence', '?')
        ok   = '✓' if item.get('citation_verified') else '✗'
        print(f'    {ok} p{p} conf={c} | {str(req)[:180]}')

# ─── Final scorecard ──────────────────────────────────────────────────────────
print()
print('=' * 70)
print('=== PRODUCTION READINESS SCORECARD ===')
print('=' * 70)

sections_total = len(score)
sections_cited = sum(1 for v in score.values() if v.get('srcs', 0) > 0)
citation_rate  = sections_cited / sections_total if sections_total else 0
cite_pct       = (total_cited / total_items * 100) if total_items else 0

checks = [
    ('Summary sections populated',  f'{sections_total}/8',          sections_total >= 7),
    ('Citation coverage (sections)', f'{citation_rate:.0%}',         citation_rate >= 0.80),
    ('Insight items extracted',      f'{total_items}',               total_items >= 20),
    ('Insight citation rate',        f'{cite_pct:.0f}%  ({total_cited}/{total_items})',
                                                                     cite_pct >= 70),
    ('Total tokens used',            f'{summary.total_tokens}',      summary.total_tokens < 200_000),
    ('Total wall time',              f'{T_total:.0f}s',              T_total < 300),
    ('Intelligence wall time',       f'{t_intel_done:.0f}s',         t_intel_done < 240),
]

all_pass = True
for name, value, passed in checks:
    icon = '✓ PASS' if passed else '✗ FAIL'
    if not passed:
        all_pass = False
    print(f'  {icon}  {name:<40} {value}')

print()
print('  Overall:', 'READY' if all_pass else 'NEEDS WORK')

# ─── Save results ─────────────────────────────────────────────────────────────
out = {
    'document_id':    str(doc.id),
    'filename':       doc.original_filename,
    'pages':          parsed.total_pages,
    'full_text_chars':len(parsed.structured_text or parsed.raw_text or ''),
    'wall_total_s':   T_total,
    'intel_total_s':  t_intel_done,
    'total_tokens':   summary.total_tokens,
    'stage_log':      stage_log,
    'score_card':     score,
    'summary_json':   sj,
    'insight_types':  [
        {
            'type':       ins.extraction_type,
            'item_count': len(ins.payload.get('items', [])),
            'confidence': ins.confidence_score,
            'token_usage':ins.token_usage,
        }
        for ins in insights
    ],
}
out_path = r'D:\RAQ-Document-summarizer\testing-docs\e2e_sync_result.json'
with open(out_path, 'w', encoding='utf-8') as fout:
    json.dump(out, fout, indent=2, default=str)

print()
print(f'Full output → {out_path}')
print('=== TEST COMPLETE ===')
