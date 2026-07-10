from django.db import models


class SummaryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ExtractionType(models.TextChoices):
    EXECUTIVE_OVERVIEW = "executive_overview", "Executive Overview"
    ELIGIBILITY_CRITERIA = "eligibility_criteria", "Eligibility Criteria"
    SUBMISSION_DEADLINES = "submission_deadlines", "Submission Deadlines"
    TECHNICAL_REQUIREMENTS = "technical_requirements", "Technical Requirements"
    SCOPE_OF_WORK = "scope_of_work", "Scope of Work"
    PAYMENT_TERMS = "payment_terms", "Payment Terms"
    PENALTIES_AND_RISKS = "penalties_and_risks", "Penalties and Risks"
    MANDATORY_DOCUMENTS = "mandatory_documents", "Mandatory Documents"
    EVALUATION_CRITERIA = "evaluation_criteria", "Evaluation Criteria"
    SET_ASIDES = "set_asides", "Set Asides"


# Extraction types run as focused LLM passes (executive overview synthesized at summary stage)
FOCUSED_EXTRACTION_TYPES = [
    ExtractionType.ELIGIBILITY_CRITERIA,
    ExtractionType.SUBMISSION_DEADLINES,
    ExtractionType.TECHNICAL_REQUIREMENTS,
    ExtractionType.SCOPE_OF_WORK,
    ExtractionType.PAYMENT_TERMS,
    ExtractionType.PENALTIES_AND_RISKS,
    ExtractionType.MANDATORY_DOCUMENTS,
    ExtractionType.SET_ASIDES,
]


class LearnedEntryKind(models.TextChoices):
    TERM = "term", "Search term"
    QUERY = "query", "Hybrid search query"


class LearnedTermSource(models.TextChoices):
    HEURISTIC = "heuristic", "Heuristic mining"
    LLM = "llm", "LLM lexicon"
    HYBRID_FEEDBACK = "hybrid_feedback", "Hybrid retrieval feedback"
    EMPTY_RETRY = "empty_retry", "Empty extraction retry"
