import zipfile
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import patch

import pytest
from bin.generator import ROOT_PATH, generate


class TestGenerator:
    @pytest.fixture
    def tmp_path(self, tmp_path):
        (tmp_path / "fake_uuid" / "g4" / "xml").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def fake_ps2pdf(self, fake_process):
        return fake_process.register(
            [
                "ps2pdf",
                "-dPDFSETTINGS=/prepress",
                "-dEPSCrop",
                fake_process.any(min=2, max=2),
            ],
            occurrences=5,
        )

    @pytest.fixture
    def fake_saxon(self, tmp_path, fake_process):
        return fake_process.register(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-warnings:recover",
                "-t",
                "-a",
                str(tmp_path / "fake_uuid" / "g4" / "xml" / "document.xml"),
            ],
            stderr=["SAXON"],
        )

    @pytest.fixture
    def fake_ahformatter(self, tmp_path, fake_process):
        return fake_process.register(
            [
                "/usr/AHFormatterV6_64/run.sh",
                "-d",
                str(tmp_path / "fake_uuid" / "g4" / "xml" / "document.fo"),
                "-o",
                str(tmp_path / "fake_uuid" / "g4" / "document.pdf"),
                "-extlevel",
                "3",
                "-i",
                str(ROOT_PATH / "inputs" / "config" / "AHFormatterSettings.xml"),
            ],
            stderr=["AHFormatter"],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "document.pdf"
            ).touch(),
        )

    @pytest.fixture(params=["IN_G4", "GUI_940"])
    def fake_saxon_metadata(self, request, tmp_path, fake_process):
        return fake_process.register(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-t",
                "-o",
                str(tmp_path / "fake_uuid" / "g4" / "metadonnees.xml"),
                str(tmp_path / "fake_uuid" / "g4" / "xml" / "document.xml"),
                str(
                    tmp_path
                    / "fake_uuid"
                    / "source"
                    / "xsl"
                    / "metadonnees"
                    / "ISO_OuvNaut.xsl"
                ),
            ],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / f"OUVNAUT_{request.param}.xml"  # FIXME
            ).touch(),
        )

    @pytest.fixture
    def mock_bootstrap_assets(self, tmp_path):
        def create_asset_dirs():
            (tmp_path / "commun").mkdir(exist_ok=True)
            ion_file = tmp_path / "source" / "xsl" / "metadonnees" / "ISO_OuvNaut.xsl"
            ion_file.parent.mkdir(parents=True, exist_ok=True)
            ion_file.touch()

        with patch(
            "bin.generator.bootstrap_assets", autospec=True
        ) as bootstrap_assets_mock:
            bootstrap_assets_mock.side_effect = create_asset_dirs
            yield bootstrap_assets_mock

    def test_basic(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        expected_steps = [
            "Étape 1 sur 7: Récupération des ressources métiers du Shom",
            "Étape 2 sur 7: Récupération des illustrations communes dans le référentiel",
            "Étape 3 sur 7: Conversion des illustrations communes",
            "Étape 4 sur 7: Conversion des illustrations de l'ouvrage",
            "Étape 5 sur 7: Récupération des sources communes",
            "Étape 6 sur 7: Génération des fichiers intermédiaires (FO)",
            "Étape 7 sur 7: Génération de l'ouvrage (PDF)",
        ]

        assert (
            tmp_path / "fake_uuid" / "g4" / "displayable_step"
        ).read_text().splitlines() == expected_steps
        assert (tmp_path / "fake_uuid" / "g4" / "stderr.log").exists()
        assert (tmp_path / "fake_uuid" / "g4" / "document.pdf").exists()
        assert not (tmp_path / "fake_uuid" / "g4" / "archive.zip").exists()

    async def test_basic_within_existing_event_loop(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

    def test_copy_shared_source(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert (tmp_path / "source").is_dir()
        assert (tmp_path / "fake_uuid" / "source").is_dir()
        assert (tmp_path / "fake_uuid" / "source" / "xsl").exists()

    def test_copy_local_source(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        (tmp_path / "fake_uuid" / "g4" / "source").mkdir(parents=True)
        (tmp_path / "fake_uuid" / "g4" / "source" / "test").touch()

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert not (tmp_path / "fake_uuid" / "g4" / "source").is_dir()
        assert (tmp_path / "fake_uuid" / "source").is_dir()
        assert (tmp_path / "fake_uuid" / "source" / "test").exists()
        assert not (tmp_path / "fake_uuid" / "source" / "xsl").exists()

    def test_idocument(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_ahformatter,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_s3_endpoint = "https://fake_s3_endpoint"
        fake_s3_source_path = "s3://fake_readable_bucket"
        fake_s3_fetch_idocument_ouvrage = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                "--recursive",
                fake_s3_source_path,
                str(tmp_path / "fake_uuid" / "g4"),
            ],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "idocument.donottouch.xml"
            ).touch(),
        )
        fake_saxon_idocument = fake_process.register(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-warnings:recover",
                "-t",
                "-a",
                str(tmp_path / "fake_uuid" / "g4" / "xml" / "document.xml"),
                "pagination=false",
            ],
            stderr=["SAXON"],
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint=fake_s3_endpoint,
            s3_source_path=fake_s3_source_path,
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
        )
        assert not fake_ps2pdf.calls
        assert fake_s3_fetch_idocument_ouvrage.calls
        assert fake_saxon_idocument.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

    def test_calmarafacon(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_s3_endpoint = "https://fake_s3_endpoint"
        fake_s3_source_path = "s3://fake_readable_bucket"

        fake_s3_fetch_calmar_ouvrage = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                "--recursive",
                fake_s3_source_path,
                str(tmp_path / "fake_uuid" / "g4"),
            ],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "calmarafacon.donottouch.xml"
            ).touch(),
        )

        fake_saxon_calmar = fake_process.register(
            [
                "java",
                "-jar",
                str(ROOT_PATH / "vendors" / "saxon" / "saxon9.jar"),
                "-warnings:recover",
                "-t",
                str(tmp_path / "fake_uuid" / "g4" / "xml" / "document.xml"),
                str(
                    tmp_path
                    / "fake_uuid"
                    / "source"
                    / "xsl"
                    / "fo"
                    / "Calmar_A_Facon.xsl"
                ),
            ],
            stderr=["SAXON CALMAR"],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "xml" / "01-FAKE_REGION_2023_local.fo"
            ).touch(),
        )

        fake_ahformatter_calmar = fake_process.register(
            [
                "/usr/AHFormatterV6_64/run.sh",
                "-d",
                str(
                    tmp_path
                    / "fake_uuid"
                    / "g4"
                    / "xml"
                    / "01-FAKE_REGION_2023_local.fo"
                ),
                "-o",
                str(tmp_path / "fake_uuid" / "g4" / "01-FAKE_REGION_2023_local.pdf"),
                "-extlevel",
                "3",
                "-i",
                str(ROOT_PATH / "inputs" / "config" / "AHFormatterSettings.xml"),
            ],
            stderr=["AHFormatter CALMAR"],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "01-FAKE_REGION_2023_local.pdf"
            ).touch(),
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint=fake_s3_endpoint,
            s3_source_path=fake_s3_source_path,
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
        )

        assert not fake_ps2pdf.calls
        assert fake_s3_fetch_calmar_ouvrage.calls
        assert fake_saxon.calls
        assert fake_saxon_calmar.calls
        assert fake_ahformatter.calls
        assert fake_ahformatter_calmar.calls
        mock_bootstrap_assets.assert_called_once()

        archive = zipfile.Path(tmp_path / "fake_uuid" / "g4" / "archive.zip")
        assert {file.name for file in archive.iterdir()} == {
            "document.pdf",
            "01-FAKE_REGION_2023_local.pdf",
        }

    def test_fetch_from_s3(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_s3_endpoint = "https://fake_s3_endpoint"
        fake_s3_source_path = "s3://fake_readable_bucket"
        fake_s3_fetch_ouvrage = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                "--recursive",
                fake_s3_source_path,
                str(tmp_path / "fake_uuid" / "g4"),
            ]
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint=fake_s3_endpoint,
            s3_source_path=fake_s3_source_path,
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert fake_s3_fetch_ouvrage.call_count() == 1
        assert fake_s3_fetch_ouvrage.first_call.args == fake_process.calls[0]

    def test_write_in_s3(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_saxon_metadata,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_s3_endpoint = "https://fake_s3_endpoint"
        fake_s3_source_path = "s3://fake_readable_bucket"
        fake_s3_destination_path = "s3://fake_writeable_bucket"

        fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                "--recursive",
                fake_s3_source_path,
                str(tmp_path / "fake_uuid" / "g4"),
            ]
        )

        fake_s3_write = fake_process.register(
            [
                "python",
                "-m",
                "awscli",
                "s3",
                "cp",
                "--endpoint-url",
                fake_s3_endpoint,
                fake_process.any(min=2, max=2),
            ],
            occurrences=4,
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint=fake_s3_endpoint,
            s3_source_path=fake_s3_source_path,
            s3_destination_path=fake_s3_destination_path,
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            metadata=True,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_saxon_metadata.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert fake_s3_write.call_count() == 4

        fake_s3_write_args = [call.args for call in fake_s3_write.calls]
        assert fake_s3_write_args == list(fake_process.calls)[-4:]

        fake_source_prefixes = [
            str(tmp_path / "fake_uuid" / "g4" / "document.pdf"),
            str(tmp_path / "fake_uuid" / "g4" / "vignette.jpg"),
            str(tmp_path / "fake_uuid" / "g4" / "stderr.log"),
            str(tmp_path / "fake_uuid" / "g4" / "OUVNAUT"),
        ]
        fake_destination_prefixes = [
            fake_s3_destination_path + "/document.pdf",
            fake_s3_destination_path + "/vignette.jpg",
            fake_s3_destination_path + "/stderr.log",
            fake_s3_destination_path + "/OUVNAUT",
        ]
        for write_in_s3_call, fake_source_prefix, fake_destination_prefix in zip(
            fake_s3_write_args,
            fake_source_prefixes,
            fake_destination_prefixes,
            strict=True,
        ):
            assert write_in_s3_call[-2].startswith(fake_source_prefix)
            assert write_in_s3_call[-1].startswith(fake_destination_prefix)

    def test_eps_common(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        folder_eps = tmp_path / "commun"
        (folder_eps / "in" / "illustrations" / "eps").mkdir(parents=True)
        (folder_eps / "in" / "illustrations" / "eps" / "fake1.eps").touch()

        (folder_eps / "illustrations" / "eps").mkdir(parents=True)
        (folder_eps / "illustrations" / "eps" / "fake2.eps").touch()
        (folder_eps / "illustrations" / "eps" / "fake3.eps").touch()

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert (tmp_path / "commun" / "illustrations" / "eps").exists()
        assert (tmp_path / "fake_uuid" / "commun" / "illustrations" / "pdf").exists()
        assert (
            tmp_path / "fake_uuid" / "commun" / "in" / "illustrations" / "pdf"
        ).exists()
        assert fake_ps2pdf.call_count() == 3
        for fake_popen in fake_ps2pdf.calls:
            *_, eps_path, pdf_path = fake_popen.args
            assert str(tmp_path / "fake_uuid" / "commun") in eps_path
            assert Path(eps_path).stem == Path(pdf_path).stem
            assert Path(pdf_path).suffix == ".pdf"

    def test_eps_ouvrage(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps").mkdir(parents=True)
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps" / "fake1.eps").touch()
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps" / "fake2.eps").touch()
        (
            tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps" / ".toignore.eps"
        ).touch()

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert (tmp_path / "fake_uuid" / "g4" / "illustrations" / "pdf").exists()

        assert fake_ps2pdf.call_count() == 2
        for fake_popen in fake_ps2pdf.calls:
            *_, eps_path, pdf_path = fake_popen.args

            stem = Path(eps_path).stem
            assert eps_path == str(
                tmp_path
                / "fake_uuid"
                / "g4"
                / "illustrations"
                / "eps"
                / (stem + ".eps")
            )
            assert pdf_path == str(
                tmp_path
                / "fake_uuid"
                / "g4"
                / "illustrations"
                / "pdf"
                / (stem + ".pdf")
            )

    def test_cleanup(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        # Structure of an "ouvrage"
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps").mkdir(parents=True)
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps" / "fake1.eps").touch()
        (tmp_path / "fake_uuid" / "g4" / "tableaux").mkdir(parents=True)

        # Files that would be generated and we want to keep
        (tmp_path / "fake_uuid" / "g4" / "document.pdf").touch()
        (tmp_path / "fake_uuid" / "g4" / "returncode").touch()

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
        )

        assert fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert set((tmp_path / "fake_uuid").glob("**/*")) == {
            tmp_path / "fake_uuid" / "g4",
            tmp_path / "fake_uuid" / "g4" / "document.pdf",
            tmp_path / "fake_uuid" / "g4" / "stderr.log",
            tmp_path / "fake_uuid" / "g4" / "returncode",
        }

    def test_cleanup_while_interrupted_progress(
        self,
        tmp_path,
        fake_process,
    ):
        fake_process.register([fake_process.any()], returncode=1)
        fake_process.keep_last_process(True)

        # Structure of an "ouvrage"
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps").mkdir(parents=True)
        (tmp_path / "fake_uuid" / "g4" / "illustrations" / "eps" / "fake1.eps").touch()
        (tmp_path / "fake_uuid" / "g4" / "tableaux").mkdir(parents=True)

        # Files that would be generated and we want to keep
        (tmp_path / "fake_uuid" / "g4" / "document.pdf").touch()
        (tmp_path / "fake_uuid" / "g4" / "returncode").touch()

        with pytest.raises(CalledProcessError):
            generate(
                tmp_path / "fake_uuid" / "g4",
                s3_endpoint="https:/fake_s3_endpoint",
                s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            )

        assert set((tmp_path / "fake_uuid").glob("**/*")) == {
            tmp_path / "fake_uuid" / "g4",
            tmp_path / "fake_uuid" / "g4" / "document.pdf",
            tmp_path / "fake_uuid" / "g4" / "stderr.log",
            tmp_path / "fake_uuid" / "g4" / "returncode",
        }

    def test_compress(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_compress = fake_process.register(
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
                f"-sOutputFile={tmp_path /'fake_uuid' / 'g4' / 'document_optimized.pdf'}",
                str(tmp_path / "fake_uuid" / "g4" / "document.pdf"),
            ],
            callback=lambda process: (
                tmp_path / "fake_uuid" / "g4" / "document_optimized.pdf"
            ).touch(),
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            compress=True,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert fake_compress.call_count() == 1
        assert fake_process.calls[-1] == fake_compress.first_call.args
        assert not (tmp_path / "fake_uuid" / "g4" / "document_optimized.pdf").exists()
        assert (tmp_path / "fake_uuid" / "g4" / "document.pdf").exists()

    def test_vignette(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_process,
        mock_bootstrap_assets,
    ):
        fake_vignette = fake_process.register(
            [
                "gs",
                "-dNOPAUSE",
                "-dBATCH",
                "-dFirstPage=1",
                "-dLastPage=1",
                "-sDEVICE=jpeg",
                fake_process.any(min=1, max=1),
                "-r150",
                "-c...setpdfwrite",
                "-f",
                str(tmp_path / "fake_uuid" / "g4" / "document.pdf"),
            ]
        )

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            vignette=True,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert fake_process.calls[-1] == fake_vignette.first_call.args

    def test_metadata(
        self,
        tmp_path,
        fake_ps2pdf,
        fake_saxon,
        fake_ahformatter,
        fake_saxon_metadata,
        mock_bootstrap_assets,
    ):
        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            metadata=True,
            cleanup=False,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        assert (
            tmp_path
            / "fake_uuid"
            / "source"
            / "xsl"
            / "metadonnees"
            / "ISO_OuvNaut.xsl"
        ).exists()

        assert fake_saxon_metadata.call_count() == 1

    def test_etape_all_steps(self, tmp_path, fake_process):
        (tmp_path / "fake_uuid" / "g4" / "document_optimized.pdf").touch()
        (tmp_path / "commun").mkdir()
        (tmp_path / "source").mkdir()

        fake_process.register([fake_process.any()])
        fake_process.keep_last_process(True)

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="fake_s3_endpoint",
            s3_source_path="fake_s3_source_path",
            s3_destination_path="fake_s3_destination_path",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            compress=True,
            vignette=True,
            metadata=True,
            cleanup=False,
        )

        assert (tmp_path / "fake_uuid" / "g4" / "displayable_step").exists()
        expected_steps = [
            "Étape 1 sur 12: Récupération des ressources métiers du Shom",
            "Étape 2 sur 12: Récupération des sources de l'ouvrage dans le référentiel",
            "Étape 3 sur 12: Récupération des illustrations communes dans le référentiel",
            "Étape 4 sur 12: Conversion des illustrations communes",
            "Étape 5 sur 12: Conversion des illustrations de l'ouvrage",
            "Étape 6 sur 12: Récupération des sources communes",
            "Étape 7 sur 12: Génération des fichiers intermédiaires (FO)",
            "Étape 8 sur 12: Génération de l'ouvrage (PDF)",
            "Étape 9 sur 12: Génération de la vignette",
            "Étape 10 sur 12: Génération des métadonnées",
            "Étape 11 sur 12: Compression du fichier PDF",
            "Étape 12 sur 12: Sauvegarde de l'ouvrage",
        ]

        assert (
            tmp_path / "fake_uuid" / "g4" / "displayable_step"
        ).read_text().splitlines() == expected_steps

    def test_etape_some_steps(self, tmp_path, fake_process):
        (tmp_path / "fake_uuid" / "g4" / "document_optimized.pdf").touch()
        (tmp_path / "commun").mkdir()
        (tmp_path / "source").mkdir()

        fake_process.register([fake_process.any()])
        fake_process.keep_last_process(True)

        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="fake_s3_endpoint",
            s3_source_path="fake_s3_source_path",
            s3_destination_path="fake_s3_destination_path",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            compress=True,
            cleanup=False,
        )

        assert (tmp_path / "fake_uuid" / "g4" / "displayable_step").exists()
        expected_steps = [
            "Étape 1 sur 10: Récupération des ressources métiers du Shom",
            "Étape 2 sur 10: Récupération des sources de l'ouvrage dans le référentiel",
            "Étape 3 sur 10: Récupération des illustrations communes dans le référentiel",
            "Étape 4 sur 10: Conversion des illustrations communes",
            "Étape 5 sur 10: Conversion des illustrations de l'ouvrage",
            "Étape 6 sur 10: Récupération des sources communes",
            "Étape 7 sur 10: Génération des fichiers intermédiaires (FO)",
            "Étape 8 sur 10: Génération de l'ouvrage (PDF)",
            "Étape 9 sur 10: Compression du fichier PDF",
            "Étape 10 sur 10: Sauvegarde de l'ouvrage",
        ]

        assert (
            tmp_path / "fake_uuid" / "g4" / "displayable_step"
        ).read_text().splitlines() == expected_steps

    def test_interrupted_progress(self, tmp_path, fake_process):
        fake_process.register([fake_process.any()], returncode=1)
        fake_process.keep_last_process(True)

        with pytest.raises(CalledProcessError):
            generate(
                tmp_path / "fake_uuid" / "g4",
                s3_endpoint="fake_s3_endpoint",
                s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            )

    def test_stderr(
        self, tmp_path, fake_ps2pdf, fake_saxon, fake_ahformatter, mock_bootstrap_assets
    ):
        generate(
            tmp_path / "fake_uuid" / "g4",
            s3_endpoint="https://fake_s3_endpoint",
            s3_inputs_bucket="s3://fake_s3_inputs_bucket",
            cleanup=False,
        )

        assert not fake_ps2pdf.calls
        assert fake_saxon.calls
        assert fake_ahformatter.calls
        mock_bootstrap_assets.assert_called_once()

        logs = (tmp_path / "fake_uuid" / "g4" / "stderr.log").read_text().splitlines()
        assert "g4 - INFO - SUBPROCESS : java -jar" in logs[0]
        assert logs[1] == "SAXON"
        assert "g4 - INFO - SUBPROCESS : /usr/AHFormatterV6_64/run.sh" in logs[2]
        assert logs[3] == "AHFormatter"
