FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.13.9 && useradd -u 10001 -r -m app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "vayu.wsgi", "-b", "0.0.0.0:8000", "-w", "4", "--access-logfile", "-"]
