from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.serializers import ProcessingJobSummarySerializer
from apps.documents.services.document_service import DocumentService
from apps.parsing.models import DocumentPage, DocumentSection
from apps.parsing.serializers import (
    DocumentPageSerializer,
    DocumentSectionSerializer,
    ParsedDocumentDetailSerializer,
    ParsedDocumentSerializer,
    ParsingStatusSerializer,
)
from apps.parsing.services.parsing_service import DocumentParsingService
from apps.processing.services.job_service import ProcessingJobService


class ParsedDocumentDetailView(RetrieveAPIView):
    serializer_class = ParsedDocumentDetailSerializer
    lookup_url_kwarg = "document_id"

    def get_object(self):
        return DocumentParsingService.get_parsed_for_document(
            self.kwargs["document_id"], user=self.request.user
        )


class ParsedDocumentPagesView(ListAPIView):
    serializer_class = DocumentPageSerializer
    pagination_class = None

    def get_queryset(self):
        parsed = DocumentParsingService.get_parsed_for_document(
            self.kwargs["document_id"], user=self.request.user
        )
        return DocumentPage.objects.filter(parsed_document=parsed).order_by("page_number")


class ParsedDocumentSectionsView(ListAPIView):
    serializer_class = DocumentSectionSerializer
    pagination_class = None

    def get_queryset(self):
        parsed = DocumentParsingService.get_parsed_for_document(
            self.kwargs["document_id"], user=self.request.user
        )
        return DocumentSection.objects.filter(parsed_document=parsed).order_by("section_order")


class ParsedDocumentPageDetailView(APIView):
    def get(self, request, document_id, page_number):
        parsed = DocumentParsingService.get_parsed_for_document(document_id, user=request.user)
        try:
            page = parsed.pages.get(page_number=page_number)
        except DocumentPage.DoesNotExist:
            from apps.core.exceptions import ValidationServiceError

            raise ValidationServiceError("Page not found.", code="page_not_found")
        return Response(DocumentPageSerializer(page).data)


class ParsingStatusView(APIView):
    def get(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        latest_job = ProcessingJobService.get_latest_job_for_document(document.id)

        parsing_status = None
        quality = None
        total_pages = None
        ocr_pages = 0

        from apps.parsing.models import ParsedDocument

        try:
            pd = ParsedDocument.objects.get(document=document)
            parsing_status = pd.parsing_status
            quality = pd.parsing_quality_score
            total_pages = pd.total_pages
            ocr_pages = pd.parsing_metadata.get("ocr_pages", 0)
        except ParsedDocument.DoesNotExist:
            pass

        payload = {
            "document_id": document.id,
            "document_status": document.status,
            "parsing_status": parsing_status,
            "parsing_quality_score": quality,
            "total_pages": total_pages,
            "ocr_pages": ocr_pages,
            "latest_job": (
                ProcessingJobSummarySerializer(latest_job).data if latest_job else None
            ),
        }
        return Response(ParsingStatusSerializer(payload).data)
