#!/usr/bin/env bash
# build.sh — runs during Render deploy

set -o errexit  # exit on error

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate