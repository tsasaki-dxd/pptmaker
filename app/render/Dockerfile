# Lambda Container Image for SlideForge Render (with LibreOffice + Poppler)
FROM public.ecr.aws/lambda/python:3.12

# LibreOffice + Poppler + Noto Sans JP
RUN dnf install -y \
      libreoffice-impress \
      libreoffice-core \
      libreoffice-headless \
      poppler-utils \
      google-noto-sans-cjk-jp-fonts \
      google-noto-sans-fonts \
      && dnf clean all

# Warm-up LibreOffice profile to reduce cold-start
RUN soffice --headless --convert-to pdf /dev/null 2>/dev/null || true

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV PYTHONPATH=${LAMBDA_TASK_ROOT}
ENV LOG_LEVEL=INFO

# Entry point: app/render/handler.py :: handler
CMD ["handler.handler"]
