#!/usr/bin/env bash

set -eo pipefail # Exit at first error, including in a pipeline
set -u # Consider unset variables as errors
set -x # Print each command before executing it

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR/..

TABLEAU_XML=$1
# ex: /tmp/blahblah/montableau.xml
TABLEAU_BASENAME=$2
# ex: tableau_test

TABLEAU_XSL=$3

PARENTDIR="$(dirname "$TABLEAU_BASENAME")"
mkdir -p $PARENTDIR

# Creation du fichier fo
java -jar vendors/saxon/saxon9.jar -warnings:fatal -t $TABLEAU_XML $TABLEAU_XSL > $TABLEAU_BASENAME.fo

# Creation du fichier pdf
/usr/AHFormatterV6_64/run.sh -d $TABLEAU_BASENAME.fo -o $TABLEAU_BASENAME.pdf -extlevel 3 -i inputs/config/AHFormatterSettings.xml

rm $TABLEAU_BASENAME.fo
