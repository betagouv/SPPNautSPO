from django.core.management.base import BaseCommand
from home.s3 import bootstrap_assets


class Command(BaseCommand):
    def handle(self, *args, **options):
        bootstrap_assets()
