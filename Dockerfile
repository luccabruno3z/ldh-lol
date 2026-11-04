# Imagen del bot de Discord (Railway). Con un Dockerfile propio el build no depende del builder que elija Railway:
# el 4/11/2026 un redeploy salió con Railpack, instaló requirements.txt (el del pipeline) y el bot no arrancó.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /app

COPY requirements-bot.txt .
RUN pip install --no-cache-dir -r requirements-bot.txt

COPY bot/ bot/

CMD ["python", "-m", "bot"]
