from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intelligence", "0003_feedback_finetune_appsetting"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentchunk",
            name="contextual_prefix",
            field=models.TextField(
                blank=True,
                default="",
                help_text="LLM-generated context snippet prepended for retrieval (Contextual Retrieval).",
            ),
        ),
    ]
