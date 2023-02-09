# syntax=docker/dockerfile:1
FROM python:3.10-slim-bullseye

RUN apt-get update
RUN apt-get install --yes alien ghostscript default-jre

COPY PDFGenerator/vendors /PDFGenerator/vendors

WORKDIR /PDFGenerator/vendors
RUN tar xzf Saxon-EE-9.2.1.1J.tar.gz
RUN alien --install --to-deb --scripts AHFormatterV6_64-6.0E-M5.x86_64.rpm
RUN rm /usr/AHFormatterV6_64/etc/AHFormatter.lic

COPY PDFGenerator/http/requirements.txt /PDFGenerator/http/requirements.txt
WORKDIR /PDFGenerator/http
RUN pip install --require-hashes --no-deps --no-cache-dir -r requirements.txt

RUN rm /usr/AHFormatterV6_64/fonts/*
# uWSGI will listen on this port
EXPOSE 8080

COPY PDFGenerator/bin /PDFGenerator/bin
COPY PDFGenerator/inputs /PDFGenerator/inputs
COPY PDFGenerator/http /PDFGenerator/http

# Create a group and user to run our app
ARG APP_USER=appuser
RUN groupadd --system ${APP_USER} && useradd --no-log-init --system --create-home --gid ${APP_USER} ${APP_USER}

RUN chown -R ${APP_USER}:${APP_USER} /usr/AHFormatterV6_64/etc /usr/AHFormatterV6_64/fonts /PDFGenerator/vendors/saxon/

# Change to a non-root user
USER ${APP_USER}:${APP_USER}

# Clevercloud S3 implementation (Cellar) only supports this signature
RUN python -m awscli configure set default.s3.signature_version s3

ENV PYTHONPATH=/PDFGenerator/http

CMD ["./services.sh"]
