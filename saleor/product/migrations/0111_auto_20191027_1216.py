# Generated by Django 2.2.6 on 2019-10-27 17:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0110_auto_20191027_1020'),
    ]

    operations = [
        migrations.RenameField(
            model_name='variantvideo',
            old_name='image',
            new_name='video',
        ),
        migrations.AddField(
            model_name='productvideo',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='productvideo',
            name='title',
            field=models.CharField(default=None, max_length=128),
        ),
    ]
