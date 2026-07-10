from django.db import models


class ParsingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ExtractionMethod(models.TextChoices):
    NATIVE_PDF = "native_pdf", "Native PDF Text"
    OCR = "ocr", "OCR (Tesseract)"
    DOCX_NATIVE = "docx_native", "DOCX Native"
