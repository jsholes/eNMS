FROM python:3.8
ENV FLASK_APP app.py
WORKDIR /app
COPY . /app
RUN pip install -r build/requirements/requirements.txt
EXPOSE 5000
CMD flask run --host=0.0.0.0
