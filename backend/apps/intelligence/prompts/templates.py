# ── Cover-page identity scan (dedicated separate API call for first pages) ─────

COVER_PAGE_IDENTITY_SYSTEM_PROMPT = """You are reading the FIRST PAGES of a construction/public-works tender document.
Your ONLY job is to extract exact project identity fields from the cover page, notice of bid, invitation to bid, bid form header, or bid schedule.

Rules:
- project_name MUST be the main project/tender title as printed on the cover page or bid schedule header.
  Example good: "FORD PARK PLAYGROUND AND RESTROOM IMPROVEMENTS"
  Example BAD (do NOT use): "PREFABRICATED RESTROOM BUILDING" (that is a spec section, not the project title).
- project_solicitation_number: find ALL reference identifiers labeled Bid No., Project No., Contract No.,
  Contract ID, Control No., Control No. Seq. No., Call Order, Spec No., RFP No., IFB No., Solicitation No.,
  File No., Job No., or similar. Return ONE item per identifier. Prefer value format '<Label>: <code>'
  (e.g. 'Project No.: AFE-H051', 'Contract ID: 81162', 'Call Order: 800').
- project_engineer: the PERSON's full name appearing after labels such as "Project Engineer:", "Engineer of Record:",
  "Designed by:", "Engineer:". Extract the name ONLY — not the firm name.
- project_architect: the PERSON's full name appearing after labels such as "Project Architect:", "Architect:",
  "Architect of Record:", "Designed by:". Extract the name ONLY — not the firm name.
- project_owner: the owner/agency entity name (e.g. "City of Beaumont", "County of Riverside", "School District").
- If a field is NOT present in the provided text, do NOT guess or fabricate it. Simply omit it.
- Every item MUST include a verbatim source_text snippet copied directly from the input.
- Respond with valid JSON only."""


def cover_page_identity_user_prompt(chunk_text: str) -> str:
    return f"""Scan the following first-page text of a tender document.
Extract ONLY the identity fields listed below. Do NOT extract anything else.

Document text (first pages):
---
{chunk_text}
---

Return JSON:
{{
  "items": [
    {{
      "requirement": "<field_name>: <exact extracted text as it appears in the document>",
      "label": "<field_name>",
      "value": "<exact extracted text>",
      "page": integer or null,
      "section": "cover page / bid notice / bid form header",
      "source_text": "verbatim excerpt from document text above",
      "confidence": 0.0 to 1.0
    }}
  ]
}}

Allowed field_name values (use EXACTLY these names):
  project_name, project_solicitation_number, project_engineer, project_architect, project_owner

For project_solicitation_number: if multiple identifiers are found (e.g. Bid No. AND Project No.), return one item per identifier, each with its own label "project_solicitation_number".
Only return items for fields you actually found in the text — omit any field not present."""


# ── Adaptive lexicon (Phase 4+) — document-specific search vocabulary ─────────

ADAPTIVE_LEXICON_SYSTEM_PROMPT = """You extract document-specific search vocabulary from bid/RFP/spec cover pages.
The full document uses unpredictable wording — capture EXACT phrases and labels from the input text.
Do NOT invent terms. Prefer short phrases (2–6 words) copied or closely paraphrased from the document.
Respond with valid JSON only."""


def adaptive_lexicon_user_prompt(cover_text: str) -> str:
    return f"""Analyze this cover/bid-notice text and extract search vocabulary for finding content later in the SAME document.

For each category below, list:
- terms: distinctive words/phrases from THIS document (exact labels, proper nouns, section names, form names)
- search_queries: 1–2 natural-language search sentences using document-specific wording

Categories (use these exact keys):
  eligibility_criteria, submission_deadlines, technical_requirements, scope_of_work,
  payment_terms, penalties_and_risks, mandatory_documents, evaluation_criteria

DOCUMENT TEXT:
---
{cover_text}
---

Return JSON:
{{
  "types": {{
    "submission_deadlines": {{
      "terms": ["Proposer's Conference", "Bid Opening"],
      "search_queries": ["When is the proposer conference and bid due date for this project?"]
    }}
  }}
}}"""


ADAPTIVE_RETRY_QUERIES_SYSTEM_PROMPT = """You help retrieve missed sections from unpredictable bid/spec documents.
Given a failed extraction category and cover-page context, propose 2–3 hybrid search queries using
document-specific language (exact labels, project name, local terminology from the cover text).
Respond with valid JSON only."""


def adaptive_retry_queries_user_prompt(extraction_type: str, cover_text: str) -> str:
    return f"""Extraction type "{extraction_type}" returned NO items from this document.
Generate search queries to find the relevant sections elsewhere in the document.

Use wording from the cover text below. Do not use generic boilerplate only.

COVER TEXT:
---
{cover_text[:8000]}
---

Return JSON:
{{
  "search_queries": [
    "query using document-specific terms",
    "another query"
  ]
}}"""


# ── Standard extraction prompts ────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an enterprise tender specification analyst extracting structured facts from tender/specification documents.

Rules:
- Extract ONLY information explicitly stated or clearly implied in the provided text.
- Do NOT invent calendar dates, times, amounts, or people/addresses not in the text.
- Every item MUST include section and a verbatim source_text snippet from the input.
- For "page": use the PDF page where source_text appears if stated in the text (e.g. "--- Page 21 ---"); otherwise omit page — do NOT infer page from clause numbers like 5.4.4 or 4.16.1.
- For "section": use the document section heading (e.g. 4.4 Commercial Terms), NOT internal paragraph sub-numbering alone (e.g. do not cite only "5.4.4" when the clause sits under section 4.4).
- Prefer exact, specification-ready statements (names, addresses, numbers, dates, and bond terms).
- If the section has no relevant content, return {"items": []}.
- Respond with valid JSON only."""

EXTRACTION_TYPE_INSTRUCTIONS = {
    "eligibility_criteria": (
        "Extract tender identification + key parties (only what is present in the text): "
        "project_name, project_owner, project_engineer, project_architect, "
        "project_sector (Public/Private), project_solicitation_number(s) — return ONE item per "
        "identifier found (Bid No., RFP No., Project No., Contract No., Advertisement #, etc.). "
        "and project_document_acquisition_note ONLY when the text says where to OBTAIN "
        "or DOWNLOAD bid documents — ONE short 'where' statement only (portal/plan room name). "
        "URLs, fees, registration, hours, and contacts go elsewhere (Events), not in this field. "
        ""
        "CRITICAL selection rules: "
        "- project_name MUST be the tender/project title from cover/notice/bid schedule header. "
        "- project_owner MUST be the explicit owner/agency entity name as written. "
        "- project_engineer: extract the firm name, government body, or individual name as written "
        "  (e.g. 'HDR Engineering Inc.', 'City Engineer', 'Jane Doe P.E.'). "
        "- project_architect: extract the firm name, government body, or individual name as written "
        "  (e.g. 'Smith Architects AIA', 'State Architect', 'John Smith'). "
        "- project_sector: only set Public if clearly a public agency bid; if unclear, omit. "
        "- project_document_acquisition_note: ONE short statement naming ONLY where to get the docs "
        "(e.g. 'Download from BidNet.', 'PlanetBids and City Purchasing plan room.'). "
        "Name portal AND plan room when both are stated. "
        "Do NOT include URLs, fees, registration, hours, contacts, or other logistics. "
        "NEVER extract bid submission instructions, offer deadlines, bond requirements, or email "
        "subject lines for submitting proposals. "
        "NEVER output 'not explicitly stated' or similar negative phrases — omit the field instead. "
        ""
        "Do NOT extract project_description here (scope_of_work handles description). "
        "For each extracted item, set requirement to '<field_name>: <exact extracted text>' and "
        "value to the exact extracted text. "
        "Field names: project_name, project_owner, project_engineer, project_architect, "
        "project_sector, project_solicitation_number, project_document_acquisition_note."
    ),
    "submission_deadlines": (
        "Extract ALL required date/time milestones from timeline tables and narrative. "
        "ALLOWED label values (use EXACTLY these, no others): "
        "bid_deadline_date_time (proposals/bids/quotes due date), "
        "bid_open_date_time (bid opening/reading date), "
        "pre_bid_deadline_date_time (pre-bid conference, proposer conference, mandatory meeting — NOT site visits), "
        "site_visit_date_time (site visit, site walkthrough, mandatory site inspection), "
        "question_deadline_date_time (questions/RFI/clarification deadline), "
        "municipal_meeting_date_time (council/board/award meeting date), "
        "project_start_date_time (contract/work start date, notice to proceed), "
        "project_end_date_time (contract/work completion date, substantial completion). "
        "Mapping rules: "
        "- 'Proposals Deadline' / 'Bids Due' / 'Quote Due' → bid_deadline_date_time. "
        "- 'Furnish quotations ... before close of business <date>' / 'Responses accepted by <date>' / "
        "'Offers due' / 'Sealed bids received until' → bid_deadline_date_time (SUBMISSION due date). "
        "- 'Pre-bid Conference' / 'Proposer Conference' / 'Mandatory Meeting' → pre_bid_deadline_date_time. "
        "- 'Site Visit' / 'Site Walkthrough' / 'Mandatory Site Inspection' → site_visit_date_time. "
        "- 'Questions Due' / 'RFI Deadline' / 'Clarification Deadline' → question_deadline_date_time. "
        "- 'Council Meeting' / 'Award Meeting' / 'Board Meeting' → municipal_meeting_date_time. "
        "- 'Delivery By' / 'Deliver By' / 'Performance Period' / 'CONTRACT TIME: N Calendar Days' "
        "→ project_end_date_time (keep duration text like '102 Calendar Days' when that is what the document states). "
        "- 'Tentative Start Date' / 'Notice to Proceed' / 'Project Start' → project_start_date_time. "
        "CRITICAL: 'Date Issued', 'Issue Date', 'Issued', 'Date of Issuance', 'Advertisement Date', "
        "and 'Dated' are NOT deadlines — these are when the document was published. NEVER map them to "
        "bid_deadline_date_time or any deadline label. Omit issue/advertisement dates entirely. "
        "bid_deadline_date_time is ALWAYS the date responses must be SUBMITTED/received, which is later "
        "than the issue date. If two dates appear (issue date + due date), pick the LATER one as bid_deadline. "
        "Set date_time to the full date+time from the document. "
        "requirement must be '<label>: <date_time>' as one line."
    ),
    "technical_requirements": (
        "Extract project_square_footage and project_location. "
        "For project_location, extract EVERY distinct place where the actual work/site is located. "
        "Include ALL of these when stated (one item per distinct description): "
        "full street address; short address; city/town/village; county or IN COUNTIES lists; "
        "district/region; road/highway/route/lane names; bridges/overpasses/interchanges; "
        "intersections and cross roads; point-to-point or corridor text (from/to, mileposts, "
        "segments); facility/building/park names; area-of-work phrases "
        "(e.g. 'state highways throughout District 8'). "
        "Keep the document wording. If LOCATION and IN COUNTIES both appear, emit both. "
        "Do NOT use only the project title when a Location/Counties/site line exists. "
        "Do NOT emit bid-opening / mailing / procurement office addresses as work sites. "
        "Do NOT capture detailed scope cable runs or equipment lists as a location. "
        "CRITICAL: every item MUST set label = 'project_location' or label = 'project_square_footage' exactly. "
        "Set requirement = '<label>: <value>' and value = extracted text. "
        "Field names: project_square_footage, project_location."
    ),
    "scope_of_work": (
        "Extract the FULL work description from ANY section that describes what work must be performed. "
        "This includes sections titled: Scope of Work, Project Description, Project Details, "
        "Description of Work, Work Summary, Scope of Services, Project Scope, Specification, "
        "Work to be Performed, Description of Services, or any similar heading. "
        "Copy the text VERBATIM — do not summarize, paraphrase, or shorten. "
        "Include every sentence, numbered item, bullet point, and sub-item exactly as written. "
        "If there are MULTIPLE scope/description sections in this chunk, extract ALL of them — "
        "concatenate them in document order separated by a blank line. "
        "Do NOT add commentary, do NOT omit lines, do NOT rewrite anything. "
        "Do NOT extract any other fields from scope_of_work. "
        "Set requirement to 'project_description: <verbatim scope text>' and value to the same verbatim text. "
        "Field names to use: project_description."
    ),
    "payment_terms": (
        "Extract the project value when present as an exact value or an exact stated range. "
        "Use the exact wording from the document (numbers and units as written). "
        "requirement must be 'project_value: <exact project value text>'. Also set value to the exact project value text. "
        "If value appears as a range, keep the range wording exactly (e.g. '$2M–$3M')."
    ),
    "penalties_and_risks": (
        "Extract ONLY explicit bid/contract bond and security deposit requirements. "
        "Bond categories to extract: "
        "bid_bond_information (bid bond, bid guarantee, bid security — amount or % of bid), "
        "payment_and_security_bond (performance bond, payment bond — post-award), "
        "maintenance_and_labor_bond (maintenance bond, warranty bond, labor bond), "
        "certified_checks (certified check, cashier check, money order as bid security), "
        "other_bonds (any other surety or deposit instrument). "
        "Set requirement as '<bond_category>: <exact text>' and label = bond_category name exactly. "
        "Set value to the exact bond details text. Set date_time to null. "
        "DO NOT extract: wage determination forms (SF-1444, WD-10), labor law compliance, "
        "insurance certificates, tax obligations, environmental regulations, or general contract terms. "
        "If no bond/security instrument is required in this document section, return {\"items\": []}."
    ),
    "mandatory_documents": (
        "Extract project_document_acquisition_note (ONE short statement naming ONLY where to "
        "obtain bid documents — portal/plan room name(s), no URLs/fees/contacts) and "
        "project_solicitation_number(s) when present. "
        "project_document_acquisition_note must name where documents are obtained — NOT bid "
        "submission or bond instructions. "
        "If the tender specifies bond/check requirements, extract under bond categories only. "
        "Allowed field_name values: project_document_acquisition_note, project_solicitation_number, "
        "bid_bond_information, payment_and_security_bond, maintenance_and_labor_bond, certified_checks, other_bonds."
    ),
    "set_asides": (
        "Extract ONLY set-aside and diversity program goals explicitly stated in the document. "
        "Programs to extract (use EXACTLY these label values): "
        "set_aside_mbe (Minority Business Enterprise, MBE — % goal or requirement), "
        "set_aside_wbe (Women Business Enterprise, WBE, Female — % goal or requirement), "
        "set_aside_dbe (Disadvantaged Business Enterprise, DBE — % goal or requirement), "
        "set_aside_dvbe (Disabled Veteran Business Enterprise, DVBE — % goal or requirement), "
        "set_aside_hub (Historically Underutilized Business, HUB — % goal or requirement), "
        "set_aside_sbe (Small Business Enterprise, SBE — % goal or requirement). "
        "Set requirement as '<label>: <exact text>' and value to the exact goal/percentage text. "
        "Only extract when a specific % goal or mandatory participation requirement is stated. "
        "Do NOT extract general equal opportunity statements with no specific program or goal. "
        "If no set-aside programs are mentioned, return {\"items\": []}."
    ),
    "evaluation_criteria": (
        "Extract NOTHING for spec-check. Return {\"items\": []}."
    ),
}


# One worked example per extraction type — enforces EXACT allowed `label` values.
# Labels mirror spec_check_fields_registry FIELD_DEFS / DEADLINE / BOND keys.
EXTRACTION_FEW_SHOT: dict[str, str] = {
    "eligibility_criteria": (
        'Example input: "REQUEST FOR QUOTATION — WICR Demolition of Excess Building. '
        'Bid No. 140P6026Q0006. Issued by: National Park Service."\n'
        'Example output: {"items": ['
        '{"requirement": "project_name: WICR Demolition of Excess Building", '
        '"label": "project_name", "value": "WICR Demolition of Excess Building", '
        '"source_text": "WICR Demolition of Excess Building", "confidence": 0.97}, '
        '{"requirement": "project_solicitation_number: 140P6026Q0006", '
        '"label": "project_solicitation_number", "value": "140P6026Q0006", '
        '"source_text": "Bid No. 140P6026Q0006", "confidence": 0.95}, '
        '{"requirement": "project_owner: National Park Service", '
        '"label": "project_owner", "value": "National Park Service", '
        '"source_text": "Issued by: National Park Service", "confidence": 0.95}]}\n'
        "Allowed label values ONLY: project_name, project_owner, project_engineer, "
        "project_architect, project_sector, project_solicitation_number, "
        "project_document_acquisition_note."
    ),
    "submission_deadlines": (
        'Example input: "DATE ISSUED 02/12/2026. PLEASE FURNISH QUOTATIONS BEFORE CLOSE OF '
        'BUSINESS 03/04/2026 1300 CST. Site Visit: February 20, 2026, 1:00 PM CST. '
        'Questions due February 23, 2026."\n'
        'Example output: {"items": ['
        '{"requirement": "bid_deadline_date_time: 03/04/2026 1300 CST", '
        '"label": "bid_deadline_date_time", "date_time": "03/04/2026 1300 CST", '
        '"source_text": "PLEASE FURNISH QUOTATIONS BEFORE CLOSE OF BUSINESS 03/04/2026 1300 CST", '
        '"confidence": 0.96}, '
        '{"requirement": "pre_bid_deadline_date_time: February 20, 2026, 1:00 PM CST", '
        '"label": "pre_bid_deadline_date_time", "date_time": "February 20, 2026, 1:00 PM CST", '
        '"source_text": "Site Visit: February 20, 2026, 1:00 PM CST", "confidence": 0.95}, '
        '{"requirement": "question_deadline_date_time: February 23, 2026", '
        '"label": "question_deadline_date_time", "date_time": "February 23, 2026", '
        '"source_text": "Questions due February 23, 2026", "confidence": 0.95}]}\n'
        'IMPORTANT: "DATE ISSUED 02/12/2026" is the publication date, NOT a deadline — it is '
        "correctly omitted from the output above. Never emit issue/advertisement dates. "
        "Allowed label values ONLY: bid_deadline_date_time, bid_open_date_time, "
        "pre_bid_deadline_date_time, question_deadline_date_time, municipal_meeting_date_time, "
        "project_start_date_time, project_end_date_time. "
        "A site visit is pre_bid_deadline_date_time, NEVER municipal_meeting_date_time."
    ),
    "technical_requirements": (
        "Example A — full address preferred over redundant bare city:\n"
        'Input: "IN THE CITY OF BELL GARDENS. Ford Park East Playground is located at '
        'John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201. Area approx 12,000 sq ft."\n'
        'Output: {"items": ['
        '{"requirement": "project_location: John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"label": "project_location", '
        '"value": "John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"source_text": "Ford Park East Playground is located at John Anson Ford Park, 8000 Park Lane, Bell Gardens, CA 90201", '
        '"confidence": 0.95}, '
        '{"requirement": "project_square_footage: approx 12,000 sq ft", '
        '"label": "project_square_footage", "value": "approx 12,000 sq ft", '
        '"source_text": "Area approx 12,000 sq ft", "confidence": 0.9}]}\n'
        'NOTE: "IN THE CITY OF BELL GARDENS" may be omitted when the full address already includes the city.\n'
        "Example B — facility name + address (combine into one value):\n"
        'Input: "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO."\n'
        'Output: {"items": [{"requirement": "project_location: Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", '
        '"label": "project_location", "value": "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", '
        '"source_text": "Union Hill Elementary School, 5242 South State Hwy ZZ, Republic, MO", "confidence": 0.93}]}\n'
        "Example C — road segment:\n"
        'Input: "Resurfacing of Main Street from 1st Avenue to 5th Avenue."\n'
        'Output: {"items": [{"requirement": "project_location: Main Street from 1st Avenue to 5th Avenue", '
        '"label": "project_location", "value": "Main Street from 1st Avenue to 5th Avenue", '
        '"source_text": "Main Street from 1st Avenue to 5th Avenue", "confidence": 0.9}]}\n'
        "Example D — point-to-point:\n"
        'Input: "Guardrail installation on SR-91 between Exit 12 and Exit 18."\n'
        'Output: {"items": [{"requirement": "project_location: SR-91 between Exit 12 and Exit 18", '
        '"label": "project_location", "value": "SR-91 between Exit 12 and Exit 18", '
        '"source_text": "SR-91 between Exit 12 and Exit 18", "confidence": 0.9}]}\n'
        "Example E — multiple distinct sites (one item each):\n"
        'Input: "Work at Site A: 100 Oak Street, Springfield, IL and Site B: 200 Elm Avenue, Springfield, IL."\n'
        'Output: {"items": ['
        '{"requirement": "project_location: 100 Oak Street, Springfield, IL", '
        '"label": "project_location", "value": "100 Oak Street, Springfield, IL", '
        '"source_text": "Site A: 100 Oak Street, Springfield, IL", "confidence": 0.92}, '
        '{"requirement": "project_location: 200 Elm Avenue, Springfield, IL", '
        '"label": "project_location", "value": "200 Elm Avenue, Springfield, IL", '
        '"source_text": "Site B: 200 Elm Avenue, Springfield, IL", "confidence": 0.92}]}\n'
        "Example F — building/site name only (no address stated in doc):\n"
        'Input: "Renovation of the Ford Park East Playground. No street address provided."\n'
        'Output: {"items": [{"requirement": "project_location: Ford Park East Playground", '
        '"label": "project_location", "value": "Ford Park East Playground", '
        '"source_text": "Renovation of the Ford Park East Playground", "confidence": 0.8}]}\n'
        "Example G — district / corridor + counties (keep both):\n"
        'Input: "LOCATION: District 8 – 2026 Paint Striping. IN COUNTIES: BOYD, BROWN, CALDWELL."\n'
        'Output: {"items": ['
        '{"requirement": "project_location: District 8 – 2026 Paint Striping", '
        '"label": "project_location", "value": "District 8 – 2026 Paint Striping", '
        '"source_text": "LOCATION: District 8 – 2026 Paint Striping", "confidence": 0.95}, '
        '{"requirement": "project_location: Counties: BOYD, BROWN, CALDWELL", '
        '"label": "project_location", "value": "Counties: BOYD, BROWN, CALDWELL", '
        '"source_text": "IN COUNTIES: BOYD, BROWN, CALDWELL", "confidence": 0.95}]}\n'
        "Allowed label values ONLY: project_location, project_square_footage."
    ),
    "scope_of_work": (
        'Example input: "SCOPE OF WORK\\n'
        '1. Demolition and removal of existing building per drawings.\\n'
        '2. Site grading and earthwork as specified in Section 02200.\\n'
        '3. Installation of new storm drainage system including 18-inch RCP pipe.\\n'
        'All work shall conform to the Contract Documents and all applicable codes."\n'
        'Example output: {"items": ['
        '{"requirement": "project_description: 1. Demolition and removal of existing building per drawings. '
        '2. Site grading and earthwork as specified in Section 02200. '
        '3. Installation of new storm drainage system including 18-inch RCP pipe. '
        'All work shall conform to the Contract Documents and all applicable codes.", '
        '"label": "project_description", '
        '"value": "1. Demolition and removal of existing building per drawings. '
        '2. Site grading and earthwork as specified in Section 02200. '
        '3. Installation of new storm drainage system including 18-inch RCP pipe. '
        'All work shall conform to the Contract Documents and all applicable codes.", '
        '"source_text": "1. Demolition and removal of existing building per drawings. '
        '2. Site grading and earthwork as specified in Section 02200. '
        '3. Installation of new storm drainage system including 18-inch RCP pipe. '
        'All work shall conform to the Contract Documents and all applicable codes.", '
        '"confidence": 0.97}]}\n'
        "Allowed label values ONLY: project_description."
    ),
    "payment_terms": (
        'Example input: "The estimated project value is between $500,000 and $750,000."\n'
        'Example output: {"items": ['
        '{"requirement": "project_value: $500,000 to $750,000", '
        '"label": "project_value", "value": "$500,000 to $750,000", '
        '"source_text": "estimated project value is between $500,000 and $750,000", '
        '"confidence": 0.9}]}\n'
        "Allowed label values ONLY: project_value. "
        "If no project value/budget stated, return {\"items\": []}."
    ),
    "penalties_and_risks": (
        'Example input: "Your bid shall be accompanied by a bid bond or guarantee of five '
        'percent (5%) of the amount of the bid."\n'
        'Example output: {"items": ['
        '{"requirement": "bid_bond_information: bid bond or guarantee of five percent (5%) of the bid", '
        '"label": "bid_bond_information", '
        '"value": "bid bond or guarantee of five percent (5%) of the amount of the bid", '
        '"date_time": null, '
        '"source_text": "Your bid shall be accompanied by a bid bond or guarantee of five percent (5%) of the amount of the bid", '
        '"confidence": 0.95}]}\n'
        "Allowed label values ONLY: bid_bond_information, payment_and_security_bond, "
        "maintenance_bond, certified_checks, other_bonds. "
        "Do NOT extract wage forms (SF-1444), insurance, or tax obligations as bonds."
    ),
    "mandatory_documents": (
        'Example input: "Documents may be downloaded from www.sam.gov. Solicitation 407973-2."\n'
        'Example output: {"items": ['
        '{"requirement": "project_document_acquisition_note: Download from www.sam.gov", '
        '"label": "project_document_acquisition_note", "value": "Download from www.sam.gov", '
        '"source_text": "Documents may be downloaded from www.sam.gov", "confidence": 0.92}, '
        '{"requirement": "project_solicitation_number: 407973-2", '
        '"label": "project_solicitation_number", "value": "407973-2", '
        '"source_text": "Solicitation 407973-2", "confidence": 0.95}]}\n'
        "Allowed label values ONLY: project_document_acquisition_note, "
        "project_solicitation_number, bid_bond_information, payment_and_security_bond, "
        "maintenance_bond, certified_checks, other_bonds."
    ),
}


def extraction_user_prompt(
    extraction_type: str,
    chunk_text: str,
    section_title: str,
    known_context: dict | None = None,
) -> str:
    instruction = EXTRACTION_TYPE_INSTRUCTIONS.get(
        extraction_type, "Extract all tender specification-critical information in this category."
    )
    few_shot = EXTRACTION_FEW_SHOT.get(extraction_type, "")
    few_shot_block = f"\n{few_shot}\n" if few_shot else ""

    # A5 — prior-context injection: feed already-known identity so scattered fields
    # cite the correct project and dedup against the right entity.
    context_block = ""
    if known_context:
        known = ", ".join(
            f"{k}={v}" for k, v in known_context.items() if v
        )
        if known:
            context_block = (
                f"\nKnown about this document (for grounding only — do NOT re-output "
                f"unless this section restates it): {known}\n"
            )

    return f"""Extraction focus: {extraction_type.replace('_', ' ').title()}
Task: {instruction}
{few_shot_block}{context_block}
Document section context (use for section field): {section_title}

Document text:
---
{chunk_text}
---

Return JSON:
{{
  "items": [
    {{
      "requirement": "clear spec-ready statement (for dates: 'Label: date, time, or URL')",
      "severity": "critical | medium | low (DO NOT include for spec-check; omit for all bond extraction and date extraction)",
      "label": "short deadline name (optional)",
      "date_time": "full date and time from document, or null",
      "value": "URL or non-date detail (e.g. portal link), or null",
      "page": integer or null,
      "section": "document section heading or clause ref under that heading",
      "source_text": "verbatim excerpt from document text above",
      "confidence": 0.0 to 1.0
    }}
  ]
}}"""


# ── HyDE (C2) — Hypothetical Document Embedding ───────────────────────────────
# Generate a plausible document passage matching the search intent, embed THAT to
# retrieve by answer-similarity. Recovers vocab-mismatch misses (e.g. generic
# "scope of work" query vs document's "furnish labor for fuel tank demolition").
HYDE_SYSTEM_PROMPT = (
    "You write short, realistic excerpts from US government / public-works bid, "
    "RFP, RFQ, and IFB documents. Given a search intent, produce a 1–3 sentence "
    "passage as it would literally appear in such a document — using the concrete "
    "contractual phrasing real solicitations use (e.g. 'The Contractor shall "
    "furnish all labor, equipment, and materials…'). Do not explain. Output only "
    "the passage text as JSON."
)


def hyde_user_prompt(query: str) -> str:
    return (
        f"Search intent: {query}\n\n"
        "Write a hypothetical document passage that would best match this intent "
        'in a real solicitation. Return JSON: {"passage": "<1-3 sentence excerpt>"}'
    )


# Legacy summary LLM prompts removed — spec-check uses deterministic field builder.
SUMMARY_SYSTEM_PROMPT = ""
SUMMARY_OUTPUT_SCHEMA = ""


def build_operational_scope_guidance(extractions: dict) -> str:
    return ""


def summary_user_prompt(extractions_json: str, document_name: str) -> str:
    return ""
