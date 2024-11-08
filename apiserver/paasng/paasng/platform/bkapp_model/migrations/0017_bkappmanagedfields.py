# Generated by Django 3.2.25 on 2024-11-08 07:11

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('modules', '0016_auto_20240904_1439'),
        ('bkapp_model', '0016_processservicesflag'),
    ]

    operations = [
        migrations.CreateModel(
            name='BkAppManagedFields',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region', models.CharField(help_text='部署区域', max_length=32)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('manager', models.CharField(help_text='管理者类型', max_length=20)),
                ('fields', models.JSONField(default=[], help_text='所管理的字段')),
                ('module', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name='managed_fields', to='modules.module')),
            ],
            options={
                'unique_together': {('module', 'manager')},
            },
        ),
    ]
