# Generated migration for Active Learning Loop models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '1075_add_performance_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='SuggestionFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('suggestion_type', models.CharField(choices=[('tag', 'Tag'), ('correspondent', 'Correspondent'), ('document_type', 'Document Type'), ('storage_path', 'Storage Path'), ('custom_field', 'Custom Field'), ('workflow', 'Workflow'), ('title', 'Title')], db_index=True, max_length=20)),
                ('suggested_value_id', models.IntegerField(blank=True, help_text='ID of suggested object (for FK suggestions)', null=True)),
                ('suggested_value_text', models.TextField(blank=True, help_text='Text value for non-FK suggestions')),
                ('confidence', models.FloatField(help_text='AI confidence score (0.0 - 1.0)')),
                ('user_action', models.CharField(choices=[('accepted', 'Accepted'), ('rejected', 'Rejected'), ('modified', 'Modified'), ('ignored', 'Ignored')], db_index=True, max_length=20)),
                ('actual_value_id', models.IntegerField(blank=True, help_text='ID of actual chosen value (if different from suggestion)', null=True)),
                ('actual_value_text', models.TextField(blank=True, help_text='Actual text value chosen by user')),
                ('document_text_sample', models.TextField(blank=True, help_text='Sample of document text for retraining')),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional metadata (entities extracted, etc.)')),
                ('used_for_training', models.BooleanField(default=False, help_text='Whether this feedback was used in retraining')),
                ('training_session_id', models.CharField(blank=True, help_text='ID of training session that used this feedback', max_length=50)),
                ('document', models.ForeignKey(help_text='Document that received AI suggestions', on_delete=django.db.models.deletion.CASCADE, related_name='ai_feedbacks', to='documents.document')),
                ('user', models.ForeignKey(blank=True, help_text='User who provided feedback', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_feedbacks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'AI Suggestion Feedback',
                'verbose_name_plural': 'AI Suggestion Feedbacks',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RetrainingSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('session_id', models.CharField(db_index=True, max_length=50, unique=True)),
                ('model_type', models.CharField(help_text='Type of model being retrained (classifier, ner, etc.)', max_length=50)),
                ('training_samples_count', models.IntegerField(default=0)),
                ('feedback_items_used', models.IntegerField(default=0)),
                ('data_period_start', models.DateTimeField(blank=True, help_text='Start of feedback data period used', null=True)),
                ('data_period_end', models.DateTimeField(blank=True, help_text='End of feedback data period used', null=True)),
                ('status', models.CharField(choices=[('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='running', max_length=20)),
                ('accuracy_before', models.FloatField(blank=True, null=True)),
                ('accuracy_after', models.FloatField(blank=True, null=True)),
                ('training_config', models.JSONField(default=dict, help_text='Training parameters and configuration')),
                ('training_metrics', models.JSONField(default=dict, help_text='Detailed training metrics (loss, validation, etc.)')),
                ('error_message', models.TextField(blank=True, help_text='Error message if training failed')),
                ('model_path', models.CharField(blank=True, help_text='Path to saved model', max_length=500)),
            ],
            options={
                'verbose_name': 'Retraining Session',
                'verbose_name_plural': 'Retraining Sessions',
                'ordering': ['-started_at'],
            },
        ),
        migrations.CreateModel(
            name='MLPerformanceMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('calculated_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('period_start', models.DateTimeField(db_index=True)),
                ('period_end', models.DateTimeField(db_index=True)),
                ('suggestion_type', models.CharField(choices=[('tag', 'Tag'), ('correspondent', 'Correspondent'), ('document_type', 'Document Type'), ('storage_path', 'Storage Path'), ('custom_field', 'Custom Field'), ('workflow', 'Workflow'), ('title', 'Title')], db_index=True, max_length=20)),
                ('total_suggestions', models.IntegerField(default=0)),
                ('accepted_count', models.IntegerField(default=0)),
                ('rejected_count', models.IntegerField(default=0)),
                ('modified_count', models.IntegerField(default=0)),
                ('ignored_count', models.IntegerField(default=0)),
                ('accuracy', models.FloatField(help_text='Acceptance rate: accepted / total')),
                ('precision', models.FloatField(blank=True, help_text='Precision considering modified as incorrect', null=True)),
                ('avg_confidence', models.FloatField(help_text='Average confidence score')),
                ('avg_confidence_accepted', models.FloatField(blank=True, help_text='Average confidence for accepted suggestions', null=True)),
                ('avg_confidence_rejected', models.FloatField(blank=True, help_text='Average confidence for rejected suggestions', null=True)),
                ('low_confidence_count', models.IntegerField(default=0, help_text='Count of suggestions with confidence < 0.7')),
                ('high_confidence_errors', models.IntegerField(default=0, help_text='Count of rejected suggestions with confidence > 0.8')),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional metric data')),
            ],
            options={
                'verbose_name': 'ML Performance Metric',
                'verbose_name_plural': 'ML Performance Metrics',
                'ordering': ['-calculated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='suggestionfeedback',
            index=models.Index(fields=['suggestion_type', 'user_action'], name='documents_s_suggest_idx'),
        ),
        migrations.AddIndex(
            model_name='suggestionfeedback',
            index=models.Index(fields=['confidence'], name='documents_s_confide_idx'),
        ),
        migrations.AddIndex(
            model_name='suggestionfeedback',
            index=models.Index(fields=['created_at', 'suggestion_type'], name='documents_s_created_idx'),
        ),
        migrations.AddIndex(
            model_name='suggestionfeedback',
            index=models.Index(fields=['used_for_training'], name='documents_s_used_fo_idx'),
        ),
        migrations.AddIndex(
            model_name='retrainingsession',
            index=models.Index(fields=['model_type', 'started_at'], name='documents_r_model_t_idx'),
        ),
        migrations.AddIndex(
            model_name='retrainingsession',
            index=models.Index(fields=['status'], name='documents_r_status_idx'),
        ),
        migrations.AddIndex(
            model_name='mlperformancemetric',
            index=models.Index(fields=['suggestion_type', 'calculated_at'], name='documents_m_suggest_idx'),
        ),
        migrations.AddIndex(
            model_name='mlperformancemetric',
            index=models.Index(fields=['period_start', 'period_end'], name='documents_m_period__idx'),
        ),
        migrations.AlterUniqueTogether(
            name='mlperformancemetric',
            unique_together={('period_start', 'period_end', 'suggestion_type')},
        ),
    ]
