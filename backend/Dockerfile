FROM python:3.12-slim

# LibreOffice for DOCX -> PDF, poppler for page counts, metric-compatible fonts for
# Cambria (Caladea) and Calibri (Carlito) so the PDF preview keeps the template's line breaks.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer poppler-utils \
      fonts-crosextra-caladea fonts-crosextra-carlito fonts-liberation fonts-dejavu-core fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Optional: drop the real Microsoft fonts (cambria.ttc, calibri.ttf, GIL_____.TTF, ariblk.ttf, segoeui.ttf)
# into ./fonts before building for pixel-identical PDFs.
COPY fonts/ /usr/local/share/fonts/custom/
RUN fc-cache -f

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
