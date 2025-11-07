FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron supervisor tzdata rsyslog \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Tallinn

WORKDIR /app
RUN mkdir -p /data /var/log/supervisor

# Copy requirements first (so Docker can cache installs)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy remaining application files and env config
COPY app/ /app/
COPY .env /app/.env

COPY crontab /tmp/crontab
RUN touch /var/log/script.log \
    && crontab /tmp/crontab \
    && rm /tmp/crontab

COPY supervisord.conf /etc/supervisor/supervisord.conf

EXPOSE 8008

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]

