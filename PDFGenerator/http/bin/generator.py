#!/usr/bin/env python
import argparse
import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from home.s3 import bootstrap_assets

ROOT_PATH = Path(__file__).parent.parent.parent

ARCHIVE_FILENAME = "archive.zip"
LOG_FILENAME = "stderr.log"


class Progress:
    current_step = 1

    def __init__(self, file: Path, step_count: int) -> None:
        self.file = file
        self.step_count = step_count

    def log_step(self, text: str) -> None:
        with self.file.open("a") as f:
            print(f"Étape {self.current_step} sur {self.step_count}: {text}", file=f)
        self.current_step += 1


# Adapted from https://stackoverflow.com/a/61478547/4554587
async def _gather_with_max_concurrency(n, *tasks):
    semaphore = asyncio.Semaphore(n)

    async def sem_task(task):
        async with semaphore:
            await task

    await asyncio.gather(*(sem_task(task) for task in tasks))


@dataclass
class Generator:
    ouvrage_path: Path
    s3_endpoint: str
    s3_inputs_bucket: str
    s3_source_path: str = None
    s3_destination_path: str = None
    compress: bool = False
    vignette: bool = False
    metadata: bool = False
    cleanup: bool = True
    logfile: Path = field(init=False)
    logger: logging.Logger = field(init=False)

    def __post_init__(self):
        self.logfile = self.ouvrage_path / LOG_FILENAME
        self.logger = logging.getLogger(self.ouvrage_path.name)
        self.logger.setLevel(logging.INFO)
        file_handler = logging.FileHandler(self.logfile)
        file_handler.setFormatter(
            logging.Formatter(
                fmt=f"%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
        )
        self.logger.addHandler(file_handler)

    def _run_and_log(self, args, check=True, **kwargs):
        self.logger.info("SUBPROCESS : %s", " ".join(args))
        with self.logfile.open("a") as log_file:
            return subprocess.run(args, stderr=log_file, check=check, **kwargs)

    async def _run_and_log_async(self, *args, **kwargs):
        self.logger.info("SUBPROCESS : %s", " ".join(args))
        with self.logfile.open("a") as log_file:
            proc = await asyncio.create_subprocess_exec(
                *args, stderr=log_file, **kwargs
            )
            returncode = await proc.wait()
            if returncode != 0:
                raise subprocess.CalledProcessError(
                    cmd=" ".join(*args), returncode=returncode
                )

    async def _convert_single_eps_to_pdf(self, eps: Path):
        pdf_dir = eps.parent.parent / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        await self._run_and_log_async(
            "ps2pdf",
            "-dPDFSETTINGS=/prepress",
            "-dEPSCrop",
            str(eps.resolve()),
            str((pdf_dir / (eps.stem + ".pdf")).resolve()),
        )

    async def _convert_eps_to_pdf(self, eps_ancestor: Path) -> None:
        convert_tasks = (
            self._convert_single_eps_to_pdf(eps)
            for eps in eps_ancestor.rglob("[!.]*.eps")
        )

        await _gather_with_max_concurrency(
            os.cpu_count(),
            *convert_tasks,
        )

    def _copy_remote_folder(self, folder_name) -> None:
        generation_path = self.ouvrage_path.parent
        mutual_folder = generation_path.parent / folder_name
        shutil.copytree(mutual_folder, generation_path / folder_name)

    def _copy_source_folder(self) -> None:
        if (self.ouvrage_path / "source").exists():
            shutil.move(
                self.ouvrage_path / "source", self.ouvrage_path.parent / "source"
            )
        else:
            self._copy_remote_folder("source")

    def _generate_fo(self) -> None:
        idocument_options = []
        if (self.ouvrage_path / "idocument.donottouch.xml").exists():
            idocument_options = ["pagination=false"]
        self._run_and_log(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-warnings:recover",
                "-t",
                "-a",
                str(self.ouvrage_path / "xml" / "document.xml"),
                *idocument_options,
            ],
            stdout=open(self.ouvrage_path / "xml" / "document.fo", "w"),
        )
        if (self.ouvrage_path / "calmarafacon.donottouch.xml").exists():
            self._run_and_log(
                [
                    "java",
                    "-jar",
                    str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                    "-warnings:recover",
                    "-t",
                    str(self.ouvrage_path / "xml" / "document.xml"),
                    str(
                        self.ouvrage_path.parent
                        / "source"
                        / "xsl"
                        / "fo"
                        / "Calmar_A_Facon.xsl"
                    ),
                ],
            )

    async def _generate_pdfs(self) -> None:
        # AHFormatter run.sh writes the command invocation in stdout.
        pdf_tasks = (
            self._run_and_log_async(
                "/usr/AHFormatterV6_64/run.sh",
                "-d",
                str(fo),
                "-o",
                str(self.ouvrage_path / f"{fo.stem}.pdf"),
                "-extlevel",
                "3",
                "-i",
                str(ROOT_PATH / "inputs" / "config" / "AHFormatterSettings.xml"),
            )
            for fo in (self.ouvrage_path / "xml").glob("*.fo")
        )
        await _gather_with_max_concurrency(os.cpu_count(), *pdf_tasks)

    def _bundle_pdfs_if_needed(self) -> None:
        all_pdfs = list(self.ouvrage_path.glob("*.pdf"))
        if len(all_pdfs) > 1:
            self.logger.info("COMPRESSING : %s files", len(all_pdfs))
            with ZipFile(
                self.ouvrage_path / ARCHIVE_FILENAME, mode="w", compression=ZIP_DEFLATED
            ) as zipfile:
                for file in all_pdfs:
                    self.logger.info("COMPRESSING : %s", file)
                    zipfile.write(file, arcname=file.name)

    def _cleanup_folders(self) -> None:
        for folder in [
            self.ouvrage_path / "illustrations",
            self.ouvrage_path / "tableaux",
            self.ouvrage_path / "xml",
            self.ouvrage_path.parent / "commun",
            self.ouvrage_path.parent / "source",
            self.ouvrage_path.parent / "inputs",
        ]:
            shutil.rmtree(folder, ignore_errors=True)

        for link_or_file in [
            self.ouvrage_path / "displayable_step",
        ]:
            link_or_file.unlink(missing_ok=True)

    def _fetch_from_s3(self) -> None:
        self._run_and_log(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                self.s3_endpoint,
                "--recursive",
                self.s3_source_path,
                str(self.ouvrage_path),
            ]
        )

    def _write_in_s3(self) -> None:
        for file in [
            self.ouvrage_path / "document.pdf",
            self.ouvrage_path / "vignette.jpg",
            self.logfile,
            *self.ouvrage_path.glob("OUVNAUT_*.xml"),
        ]:
            self._run_and_log(
                [
                    "python",
                    "-m",
                    "awscli",
                    "s3",
                    "cp",
                    "--endpoint-url",
                    self.s3_endpoint,
                    str(file),
                    self.s3_destination_path + "/" + file.name,
                ],
            )

    def _compress_ouvrage(self) -> None:
        # Ghostscript command line arguments:
        # https://ghostscript.com/docs/9.54.0/VectorDevices.htm
        self._run_and_log(
            [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dNOPAUSE",
                "-dBATCH",
                "-dPDFSETTINGS=/prepress",
                "-dColorImageResolution=150",
                "-dDownsampleColorImages=true",
                "-dColorImageDownsampleThreshold=1.0",
                "-sColorConversionStrategy=RGB",
                f"-sOutputFile={self.ouvrage_path / 'document_optimized.pdf'}",
                str(self.ouvrage_path / "document.pdf"),
            ]
        )
        (self.ouvrage_path / "document_optimized.pdf").rename(
            self.ouvrage_path / "document.pdf"
        )

    def _vignette_ouvrage(self) -> None:
        self._run_and_log(
            [
                "gs",
                "-dNOPAUSE",
                "-dBATCH",
                "-dFirstPage=1",
                "-dLastPage=1",
                "-sDEVICE=jpeg",
                "-sOutputFile=" + str(self.ouvrage_path / "vignette.jpg"),
                "-r150",
                "-c...setpdfwrite",
                "-f",
                str(self.ouvrage_path / "document.pdf"),
            ]
        )

    def _metadata_ouvrage(self) -> None:
        self._run_and_log(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-t",
                "-o",
                str(self.ouvrage_path / "metadonnees.xml"),
                str(self.ouvrage_path / "xml" / "document.xml"),
                str(
                    self.ouvrage_path.parent
                    / "source"
                    / "xsl"
                    / "metadonnees"
                    / "ISO_OuvNaut.xsl"
                ),
            ]
        )

    async def __call__(self):
        displayable_step = self.ouvrage_path / "displayable_step"

        step_count = 7 + sum(
            1
            for x in [
                self.s3_endpoint and self.s3_source_path,
                self.compress,
                self.vignette,
                self.metadata,
                self.s3_endpoint and self.s3_destination_path,
            ]
            if x
        )

        progress = Progress(displayable_step, step_count)

        try:
            progress.log_step("Récupération des ressources métiers du Shom")
            bootstrap_assets()

            if self.s3_endpoint and self.s3_source_path:
                progress.log_step(
                    "Récupération des sources de l'ouvrage dans le référentiel"
                )
                self._fetch_from_s3()

            progress.log_step(
                "Récupération des illustrations communes dans le référentiel"
            )
            self._copy_remote_folder("commun")

            progress.log_step("Conversion des illustrations communes")
            await self._convert_eps_to_pdf(self.ouvrage_path.parent / "commun")

            progress.log_step("Conversion des illustrations de l'ouvrage")
            await self._convert_eps_to_pdf(self.ouvrage_path)

            progress.log_step("Récupération des sources communes")
            self._copy_source_folder()

            progress.log_step("Génération des fichiers intermédiaires (FO)")
            self._generate_fo()

            progress.log_step("Génération de l'ouvrage (PDF)")
            await self._generate_pdfs()
            self._bundle_pdfs_if_needed()

            if self.vignette:
                progress.log_step("Génération de la vignette")
                self._vignette_ouvrage()

            if self.metadata:
                progress.log_step("Génération des métadonnées")
                self._metadata_ouvrage()

            if self.compress:
                progress.log_step("Compression du fichier PDF")
                self._compress_ouvrage()

            if self.s3_endpoint and self.s3_destination_path:
                progress.log_step("Sauvegarde de l'ouvrage")
                self._write_in_s3()
        finally:
            if self.cleanup:
                self._cleanup_folders()


async def generate(*args, **kwargs):
    await Generator(*args, **kwargs)()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ouvrage_path", type=Path)
    parser.add_argument("--s3_endpoint", required=True)
    parser.add_argument("--s3_inputs_bucket", required=True)
    parser.add_argument("--s3_source_path")
    parser.add_argument("--s3_destination_path")
    parser.add_argument("--compress", action="store_true")
    parser.add_argument("--vignette", action="store_true")
    parser.add_argument("--metadata", action="store_true")
    args = parser.parse_args()
    asyncio.run(generate(**vars(args)))
