from rest_framework import serializers

from apps.parsing.models import DocumentPage, DocumentSection, ParsedDocument


class DocumentPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentPage
        fields = (
            "id",
            "page_number",
            "extracted_text",
            "extraction_method",
            "ocr_used",
            "quality_score",
            "created_at",
        )


class DocumentSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentSection
        fields = (
            "id",
            "title",
            "content",
            "page_start",
            "page_end",
            "section_order",
            "created_at",
        )


class ParsedDocumentSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source="document.id", read_only=True)
    ocr_pages = serializers.SerializerMethodField()
    tables_count = serializers.SerializerMethodField()

    class Meta:
        model = ParsedDocument
        fields = (
            "id",
            "document_id",
            "parsing_status",
            "total_pages",
            "parsing_quality_score",
            "ocr_pages",
            "tables_count",
            "parsing_metadata",
            "created_at",
            "updated_at",
        )

    def get_ocr_pages(self, obj: ParsedDocument) -> int:
        return obj.parsing_metadata.get("ocr_pages", 0)

    def get_tables_count(self, obj: ParsedDocument) -> int:
        return len(obj.parsing_metadata.get("tables", []))


class ParsedDocumentDetailSerializer(ParsedDocumentSerializer):
    raw_text_preview = serializers.SerializerMethodField()
    structured_text_preview = serializers.SerializerMethodField()

    class Meta(ParsedDocumentSerializer.Meta):
        fields = ParsedDocumentSerializer.Meta.fields + (
            "raw_text_preview",
            "structured_text_preview",
        )

    def get_raw_text_preview(self, obj: ParsedDocument) -> str:
        text = obj.raw_text or ""
        return text[:4000] + ("…" if len(text) > 4000 else "")

    def get_structured_text_preview(self, obj: ParsedDocument) -> str:
        text = obj.structured_text or ""
        return text[:4000] + ("…" if len(text) > 4000 else "")


class ParsingStatusSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_status = serializers.CharField()
    parsing_status = serializers.CharField(allow_null=True)
    parsing_quality_score = serializers.FloatField(allow_null=True)
    total_pages = serializers.IntegerField(allow_null=True)
    ocr_pages = serializers.IntegerField()
    latest_job = serializers.DictField(allow_null=True)
