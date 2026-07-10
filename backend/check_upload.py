import requests, re

BASE = 'http://localhost:8002/api/v1'
DOC  = r'D:\RAQ-Document-summarizer\testing-docs\2-RFP 2025-06.pdf'

with open(DOC, 'rb') as f:
    r = requests.post(
        f'{BASE}/documents/upload/',
        files={'file': ('2-RFP_2025-06.pdf', f, 'application/pdf')},
        data={'tender_id': 'TEST-E2E-RFP'},
        timeout=60,
    )

html = r.text

# Find the exception_value pre block
idx = html.find('exception_value')
if idx != -1:
    snippet = html[idx:idx+2000]
    clean = re.sub(r'<[^>]+>', '', snippet)
    clean = re.sub(r'\s+', ' ', clean).strip()
    print('EXCEPTION:', clean[:600])
else:
    # Try broader search
    for marker in ('Exception Value', 'Request URL', 'Python Executable'):
        idx2 = html.find(marker)
        if idx2 != -1:
            snippet = html[max(0, idx2-100):idx2+500]
            clean = re.sub(r'<[^>]+>', '', snippet)
            clean = re.sub(r'\s+', ' ', clean).strip()
            print(f'Found [{marker}]:', clean[:400])
            print('---')
