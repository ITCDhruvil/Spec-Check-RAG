from rest_framework.response import Response
from rest_framework.views import APIView

from apps.processing.serializers import ProcessingJobDetailSerializer
from apps.processing.services.job_service import ProcessingJobService


class ProcessingJobDetailView(APIView):
    def get(self, request, job_id):
        from apps.documents.services.document_service import DocumentService

        job = ProcessingJobService.get_job(job_id)
        DocumentService.get_document(job.document_id, request.user)
        serializer = ProcessingJobDetailSerializer(job)
        return Response(serializer.data)
