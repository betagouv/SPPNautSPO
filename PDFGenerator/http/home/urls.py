"""
Router config for home module
"""
from django.urls import path

from . import views

urlpatterns = [
    path(
        "health_check/",
        views.health_check,
    ),
    path("", views.tableau, name="tableau"),
    path("publication/from_preparation/list", views.list_from_preparation),
    path("publication/from_preparation/generate", views.generate_from_preparation),
    path("publication/from_production/list", views.list_from_production),
    path("publication/from_production/generate", views.generate_from_production),
    path("publication/<slug:generation_id>/upload_input", views.upload_input),
    path(
        "publication/<slug:generation_id>/generate",
        views.generate_publication_from_upload,
    ),
    path("publication/<slug:generation_id>/", views.publication),
    path("download-url/<path:path>/", views.get_download_url),
]
