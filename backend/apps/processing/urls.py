from django.urls import path

from apps.processing.views import ProcessingJobDetailView

urlpatterns = [
    path("processing/jobs/<uuid:job_id>/", ProcessingJobDetailView.as_view(), name="job-detail"),
]
