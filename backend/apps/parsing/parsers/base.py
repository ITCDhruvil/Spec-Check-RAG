from dataclasses import dataclass, field


@dataclass
class ParsedPageResult:
    page_number: int
    extracted_text: str
    extraction_method: str
    ocr_used: bool
    quality_score: float
    is_empty: bool = False


@dataclass
class ParsedTableResult:
    page_number: int
    headers: list[str]
    rows: list[list[str]]
    raw: list[list[list[str | None]]] = field(default_factory=list)


@dataclass
class ParsedLayoutBlock:
    """Layout-aware text block for citation traceability and chunk typing."""

    block_type: str  # paragraph | heading | table
    page_number: int
    text: str
    role: str = ""
    bbox: list[float] = field(default_factory=list)  # [x0, y0, x1, y1]
    section_order: int | None = None


@dataclass
class ParsedSectionResult:
    title: str
    content: str
    page_start: int
    page_end: int
    section_order: int
    level: int = 1
    parent_section_order: int | None = None
    section_path: str = ""


@dataclass
class DocumentParseResult:
    pages: list[ParsedPageResult]
    sections: list[ParsedSectionResult]
    tables: list[ParsedTableResult]
    raw_text: str
    structured_text: str
    parsing_metadata: dict
    parsing_quality_score: float
    file_type: str
    layout_blocks: list[ParsedLayoutBlock] = field(default_factory=list)
