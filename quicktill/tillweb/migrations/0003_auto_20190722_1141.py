# Generated by Django 2.2.3 on 2019-07-22 11:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tillweb', '0002_till_money_symbol'),
    ]

    operations = [
        migrations.AlterField(
            model_name='access',
            name='permission',
            field=models.CharField(choices=[('R', 'Read-only'), ('M', 'Read/write, following till permissions'), ('F', 'Full access, ignoring till permissions')], max_length=1),
        ),
    ]
