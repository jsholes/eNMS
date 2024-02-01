FROM python:3.8
WORKDIR /app
ENV FLASK_APP app.py
COPY . /app
RUN pip install -r build/requirements/requirements.txt
RUN pip install -r build/requirements/requirements_optional.txt
RUN pip install -r build/requirements/requirements_db.txt
EXPOSE 5000
CMD gunicorn --config gunicorn.py app:app
