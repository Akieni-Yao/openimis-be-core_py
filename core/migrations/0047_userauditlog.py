# Generated by Django 3.2.25 on 2025-03-18 12:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('location', '0034_auto_20250106_1415'),
        ('policyholder', '0038_auto_20250227_1613'),
        ('core', '0046_auto_20250227_1613'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserAuditLog',
            fields=[
                ('id', models.UUIDField(db_column='UUID', default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=255, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('details', models.TextField(null=True)),
                ('fosa', models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='audit_fosa_logs', to='location.healthfacility')),
                ('policy_holder', models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='user_policy_holder_logs', to='policyholder.policyholder')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblUserAuditLog',
                'managed': True,
            },
        ),
    ]
