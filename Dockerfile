FROM python:3.13-slim

EXPOSE 80/tcp

RUN mkdir /root/app
WORKDIR /root/app

ENV TZ Europe/Moscow
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
RUN export PYTHONDONTWRITEBYTECODE=1
RUN export PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip

COPY ./requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY .env.example .env
COPY ./src ./src

ENTRYPOINT ["python", "-u", "-m", "src.main"]
