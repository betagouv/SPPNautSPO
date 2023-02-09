import datetime
import uuid
from pathlib import Path

from bin.generator import generate
from decouple import config
from home.s3 import get_generated_pdf_ouvrages, get_source_xml_ouvrages
from workers import procrastinate_app

S3_BUCKET_REFERENTIEL_PRODUCTION = config("S3_BUCKET_REFERENTIEL_PRODUCTION")
S3_BUCKET_GENERATED_PRODUCTION = config("S3_BUCKET_GENERATED_PRODUCTION")
S3_ENDPOINT = config("S3_ENDPOINT")


@procrastinate_app.task(name="generate_publication_from_referentiel")
def generate_publication_from_referentiel(
    *,
    ouvrage: str,
    s3_endpoint: str,
    s3_inputs_bucket: str,
    s3_source_path: str,
    s3_destination_path: str,
):
    generation_id = uuid.uuid4()
    ouvrage_path = Path(config("HOME_GENERATION_PATH")) / str(generation_id) / ouvrage
    ouvrage_path.mkdir(parents=True)

    generate(
        ouvrage_path,
        s3_endpoint=s3_endpoint,
        s3_inputs_bucket=s3_inputs_bucket,
        s3_source_path=s3_source_path,
        s3_destination_path=s3_destination_path,
        compress=True,
        vignette=True,
        metadata=True,
        cleanup=True,
    )


@procrastinate_app.periodic(cron="5 0 * * *")
@procrastinate_app.task
async def generate_all_updated_ouvrage_from_production(timestamp):
    source_xml_ouvrages = get_source_xml_ouvrages()
    generated_pdf_ouvrages = get_generated_pdf_ouvrages()
    ouvrages_to_generate = []
    for source_xml_ouvrage, source_xml_ouvrage_date in source_xml_ouvrages.items():
        last_generated_pdf_date = generated_pdf_ouvrages.get(
            source_xml_ouvrage,
            datetime.datetime.fromtimestamp(0, datetime.timezone.utc),
        )
        if last_generated_pdf_date < source_xml_ouvrage_date:
            ouvrages_to_generate.append(source_xml_ouvrage)

    for source_xml_ouvrage in ouvrages_to_generate:
        await generate_publication_from_referentiel.defer_async(
            ouvrage=source_xml_ouvrage,
            s3_endpoint=S3_ENDPOINT,
            s3_inputs_bucket=f"s3://{S3_BUCKET_REFERENTIEL_PRODUCTION}",
            s3_source_path=f"s3://{S3_BUCKET_REFERENTIEL_PRODUCTION}/{source_xml_ouvrage}",
            s3_destination_path=f"s3://{S3_BUCKET_GENERATED_PRODUCTION}/{source_xml_ouvrage}",
        )

    return ouvrages_to_generate
