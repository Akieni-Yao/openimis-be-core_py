# Generated by Django 3.2.21 on 2024-08-12 13:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_alter_camunotification_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='camunotification',
            name='portal_redirect_url',
            field=models.CharField(blank=True, db_column='PortalRedirectURL', max_length=255, null=True),
        ),
    ]
