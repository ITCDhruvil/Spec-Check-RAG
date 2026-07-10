# Generated manually for learned extraction term cache

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intelligence", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearnedExtractionTerm",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "extraction_type",
                    models.CharField(
                        choices=[
                            ("executive_overview", "Executive Overview"),
                            ("eligibility_criteria", "Eligibility Criteria"),
                            ("submission_deadlines", "Submission Deadlines"),
                            ("technical_requirements", "Technical Requirements"),
                            ("scope_of_work", "Scope of Work"),
                            ("payment_terms", "Payment Terms"),
                            ("penalties_and_risks", "Penalties and Risks"),
                            ("mandatory_documents", "Mandatory Documents"),
                            ("evaluation_criteria", "Evaluation Criteria"),
                        ],
                        db_index=True,
                        max_length=64,
                    ),
                ),
                (
                    "entry_kind",
                    models.CharField(
                        choices=[("term", "Search term"), ("query", "Hybrid search query")],
                        db_index=True,
                        default="term",
                        max_length=16,
                    ),
                ),
                (
                    "term_normalized",
                    models.CharField(
                        db_index=True,
                        help_text="Lowercase dedupe key",
                        max_length=256,
                    ),
                ),
                (
                    "term_display",
                    models.CharField(
                        help_text="Preferred display text (latest seen casing)",
                        max_length=512,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("heuristic", "Heuristic mining"),
                            ("llm", "LLM lexicon"),
                            ("hybrid_feedback", "Hybrid retrieval feedback"),
                            ("empty_retry", "Empty extraction retry"),
                        ],
                        default="heuristic",
                        max_length=32,
                    ),
                ),
                ("hit_count", models.PositiveIntegerField(default=1)),
                ("document_count", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-hit_count", "term_display"],
            },
        ),
        migrations.AddIndex(
            model_name="learnedextractionterm",
            index=models.Index(
                fields=["extraction_type", "entry_kind", "is_active"],
                name="intelligenc_extract_6f2b0d_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="learnedextractionterm",
            constraint=models.UniqueConstraint(
                fields=("extraction_type", "entry_kind", "term_normalized"),
                name="uniq_learned_term_per_type_kind",
            ),
        ),
    ]
