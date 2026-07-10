from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_add_indexed_chunk_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentvectorindex",
            name="embedding_model_version",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Embedding model version/id used at index time.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="documentvectorindex",
            name="vector_backend",
            field=models.CharField(
                default="chroma",
                help_text="chroma | azure_search",
                max_length=32,
            ),
        ),
    ]
