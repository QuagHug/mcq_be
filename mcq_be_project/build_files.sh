pip3 install -r requirements.txt
mkdir -p dist
touch dist/.placeholder
echo "Starting Django server on port ${PORT:-8000}..."
python3 manage.py runserver 0.0.0.0:${PORT:-8000}