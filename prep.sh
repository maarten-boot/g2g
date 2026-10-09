#! /bin/bash

rm -rf venv
make venv
source ./venv/bin/activate

(
    cd pSwai

    ./manage.py makemigrations
    ./manage.py migrate

    # ./manage.py collectstatic
    # ./manage.py createsuperuser admin
    # ./manage.py runserver --insecure
)

make restart
