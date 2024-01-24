FROM python:3.8
RUN mkdir /app
WORKDIR /app/
ADD . /app/
RUN pip3 install -r build/requirements/requirements.txt
CMD ["python", "/app/app.py"]