##

source ~/DEV/Django/swai/bin/activate
pip install -r requirements.txt

./manage.py migrate
./manage.py collectstatic
./manage.py createsuperuser admin
./manage.py runserver --insecure


