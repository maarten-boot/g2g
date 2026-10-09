#! /bin/bash
set -e

rm -rf venv
make venv
source ./venv/bin/activate

(
    cd pSwai

    # migrations are made during development and committed; here we only apply them.
    # fail if the models have changes that have no migration yet
    ./manage.py makemigrations --check --dry-run
    ./manage.py migrate

    # ./manage.py collectstatic
    # ./manage.py createsuperuser admin
    # ./manage.py runserver --insecure
)

make restart
