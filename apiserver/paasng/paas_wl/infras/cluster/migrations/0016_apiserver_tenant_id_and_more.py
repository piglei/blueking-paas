# Generated by Django 4.2.16 on 2025-01-16 07:37

from django.db import migrations, models
import paas_wl.infras.cluster.models


class Migration(migrations.Migration):

    dependencies = [
        ("cluster", "0015_remove_apiserver_overridden_hostname"),
    ]

    operations = [
        migrations.AddField(
            model_name="apiserver",
            name="tenant_id",
            field=models.CharField(
                db_index=True,
                default="default",
                help_text="本条数据的所属租户",
                max_length=32,
                verbose_name="租户 ID",
            ),
        ),
        migrations.AddField(
            model_name="clusterelasticsearchconfig",
            name="tenant_id",
            field=models.CharField(
                db_index=True,
                default="default",
                help_text="本条数据的所属租户",
                max_length=32,
                verbose_name="租户 ID",
            ),
        ),
        migrations.AlterField(
            model_name="cluster",
            name="exposed_url_type",
            field=models.IntegerField(default=1, help_text="应用的访问地址类型"),
        ),
        migrations.AlterField(
            model_name="cluster",
            name="tenant_id",
            field=models.CharField(
                db_index=True,
                default="default",
                help_text="本条数据的所属租户",
                max_length=32,
                verbose_name="租户 ID",
            ),
        ),
        migrations.AlterField(
            model_name="clusterallocationpolicy",
            name="allocation_policy",
            field=paas_wl.infras.cluster.models.AllocationPolicyField(
                default=None, help_text="统一分配策略", null=True
            ),
        ),
        migrations.AlterField(
            model_name="clusterallocationpolicy",
            name="allocation_precedence_policies",
            field=paas_wl.infras.cluster.models.AllocationPrecedencePoliciesField(
                default=list, help_text="规则分配优先策略"
            ),
        ),
        migrations.AlterField(
            model_name="clusterallocationpolicy",
            name="tenant_id",
            field=models.CharField(
                default="default",
                help_text="本条数据的所属租户",
                max_length=32,
                unique=True,
                verbose_name="租户 ID",
            ),
        ),
    ]
