#! /bin/bash

rm -rf venv bin include lib lib84

VENV="$(realpath . )/venv"
python -m venv venv
python -m venv --upgrade venv
source $VENV/bin/activate
pip install -U -r requirements.txt

bash reformat.sh
cd pSwai

./manage.py makemigrations
./manage.py migrate

# ./manage.py collectstatic
# ./manage.py createsuperuser admin
# ./manage.py runserver --insecure

sudo systemctl restart gunicorn003
