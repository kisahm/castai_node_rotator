FROM python:3.9

ENV PATH /usr/local/bin:$PATH

ENV PYTHONUNBUFFERED 1

RUN mkdir /app
COPY /src /app
WORKDIR /app

RUN pip3 install -r requirements.txt

CMD ["python", "src.py"]