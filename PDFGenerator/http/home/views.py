import datetime
import logging
import shutil
import subprocess
import uuid
from http import HTTPStatus
from itertools import takewhile
from pathlib import Path

import sentry_sdk
from bin.generator import ARCHIVE_FILENAME, LOG_FILENAME
from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import FormView

from .forms import UploadDirectoryFileForm, UploadFileForm
from .s3 import (
    bootstrap_assets,
    get_presigned_url,
    list_generated_documents_by_ouvrages,
    list_ouvrages_en_preparation,
)

RETURN_CODE_FILENAME = "returncode"


class Tableau(FormView):
    form_class = UploadFileForm
    template_name = "index.html"

    def form_valid(self, form):
        bootstrap_assets()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        name = Path(form.cleaned_data["file"].name).stem
        basename = f"{name}_{timestamp}"
        subprocess.run(
            [
                "../bin/generate_tableau.sh",
                form.cleaned_data["file"].temporary_file_path(),
                settings.HOME_GENERATION_PATH / "tableaux" / basename,
                settings.HOME_GENERATION_PATH
                / "source"
                / "xsl"
                / "fo"
                / "tableauTaP.xsl",
            ],
            check=True,
        )
        return FileResponse(
            (settings.HOME_GENERATION_PATH / "tableaux" / f"{basename}.pdf").open("rb")
        )


tableau = Tableau.as_view()


class UploadInput(FormView):
    form_class = UploadDirectoryFileForm
    http_method_names = ["post"]

    def post(self, request, generation_id, *args, **kwargs):
        self.generation_id = generation_id
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # FIXME : tester sous windows

        input_file_path_in_generation_folder = (
            settings.HOME_GENERATION_PATH
            / self.generation_id
            / Path(form.cleaned_data["webkitRelativePath"])
        )
        input_file_path_in_generation_folder.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(
            form.cleaned_data["file"].temporary_file_path(),
            input_file_path_in_generation_folder,
        )

        return HttpResponse(status=HTTPStatus.ACCEPTED)

    def form_invalid(self, form):
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)


upload_input = UploadInput.as_view()


@require_POST
def generate_publication_from_upload(request, generation_id):

    try:
        publication_path = _get_publication_path(generation_id)
    except FileNotFoundError as err:
        sentry_sdk.capture_exception(err)
        return HttpResponse(status=HTTPStatus.BAD_REQUEST)

    subprocess.Popen(
        [
            settings.BIN_DIR / "echo_returncode_in.py",
            publication_path / RETURN_CODE_FILENAME,
            settings.BASE_DIR / "bin" / "generator.py",
            publication_path,
            "--s3_endpoint",
            settings.S3_ENDPOINT,
            "--s3_inputs_bucket",
            f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}",
        ]
    )
    return HttpResponse(status=HTTPStatus.ACCEPTED)


@require_GET
def publication(request, generation_id):

    try:
        publication_path = _get_publication_path(generation_id)
    except FileNotFoundError:
        return HttpResponse(status=HTTPStatus.CONFLICT)

    return_code_path = publication_path / RETURN_CODE_FILENAME
    if not return_code_path.exists():
        try:
            displayable_step = (
                (publication_path / "displayable_step").read_text().splitlines()[-1]
            )
        except (FileNotFoundError, IndexError):
            displayable_step = "Démarrage…"
        return HttpResponse(
            displayable_step,
            content_type="text/plain; charset=utf-8",
            status=HTTPStatus.NOT_FOUND,
        )

    return_code = return_code_path.read_text()
    if int(return_code) != 0:
        stderr = (publication_path / LOG_FILENAME).read_text().splitlines()

        for line in stderr:
            logging.warning(line)
        logging.error(f"Publication {publication_path.name} failed to generate")

        non_python_stderr = [
            stderr_line
            for stderr_line in takewhile(
                lambda x: not x.startswith("Traceback (most recent call last):"), stderr
            )
        ]

        return HttpResponse(
            "\n".join(non_python_stderr),
            content_type="text/plain; charset=utf-8",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    if (publication_path / ARCHIVE_FILENAME).exists():
        return FileResponse(
            (publication_path / ARCHIVE_FILENAME).open("rb"),
            filename=f"{publication_path.name}.zip",
        )
    return FileResponse(
        (publication_path / "document.pdf").open("rb"),
        filename=f"{publication_path.name}.pdf",
    )


@require_GET
def get_download_url(request, path):
    return HttpResponse(get_presigned_url(path))


def _get_publication_path(generation_id) -> Path:
    upload_folder = settings.HOME_GENERATION_PATH / generation_id
    publication_common_inputs = ["commun", "source", "www"]
    directory_content = [
        file
        for file in upload_folder.iterdir()
        if file.name not in publication_common_inputs
    ]

    if len(directory_content) == 0:
        raise FileNotFoundError("No publication directory found in the upload folder")
    if len(directory_content) > 1:
        raise FileNotFoundError(
            "More than 1 publication folder found, we can't know which publication should be generated"
        )

    return directory_content[0]


@require_GET
def list_from_preparation(request):
    ouvrages = list_ouvrages_en_preparation()
    # Safe=False because a array is returned (not a dict)
    return JsonResponse(ouvrages, safe=False)


@require_GET
def list_from_production(request):
    ouvrages = list_generated_documents_by_ouvrages()
    # Safe=False because a array is returned (not a dict)
    return JsonResponse(ouvrages, safe=False)


def _generate_publication_from_referentiel(request, args_callable):
    generation_id = uuid.uuid4()
    ouvrage = request.POST["ouvrage"]

    publication_path = settings.HOME_GENERATION_PATH / str(generation_id) / ouvrage
    publication_path.mkdir(parents=True)

    subprocess.Popen(
        [
            settings.BIN_DIR / "echo_returncode_in.py",
            publication_path / RETURN_CODE_FILENAME,
            settings.BASE_DIR / "bin" / "generator.py",
            publication_path,
            "--s3_endpoint",
            settings.S3_ENDPOINT,
            "--s3_inputs_bucket",
            f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}",
            *args_callable(ouvrage),
        ]
    )

    return JsonResponse({"generation_id": generation_id}, status=HTTPStatus.ACCEPTED)


@require_POST
def generate_from_preparation(request) -> JsonResponse:
    def specific_args_generator_sh(ouvrage):
        return [
            "--s3_source_path",
            f"s3://{settings.S3_BUCKET_REFERENTIEL_PREPARATION}/{ouvrage}",
        ]

    return _generate_publication_from_referentiel(request, specific_args_generator_sh)


@require_POST
def generate_from_production(request) -> JsonResponse:
    def generator_sh_args(ouvrage):
        return [
            "--s3_source_path",
            f"s3://{settings.S3_BUCKET_REFERENTIEL_PRODUCTION}/{ouvrage}",
            "--s3_destination_path",
            f"s3://{settings.S3_BUCKET_GENERATED_PRODUCTION}/{ouvrage}",
            "--compress",
            "--vignette",
            "--metadata",
        ]

    return _generate_publication_from_referentiel(request, generator_sh_args)


@require_GET
def health_check(request):
    return JsonResponse({"status": "ok"})
