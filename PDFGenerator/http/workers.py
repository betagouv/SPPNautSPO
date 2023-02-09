from core import error_reporting
from decouple import config
from procrastinate import AiopgConnector, App
from procrastinate.testing import InMemoryConnector

error_reporting.init()

if config("TEST", default=False, cast=bool):
    connector = InMemoryConnector()
else:
    connector = AiopgConnector(dsn=config("POSTGRESQL_ADDON_URI"))

procrastinate_app = App(connector=connector, import_paths=["home.tasks"])

procrastinate_app.open()
