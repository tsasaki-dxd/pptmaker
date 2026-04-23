# Lambda Container Image for SlideForge Render (LibreOffice + Poppler + Noto Sans JP)
#
# Uses a Debian slim base + AWS Lambda Runtime Interface Client (awslambdaric)
# instead of the AL2023-based public.ecr.aws/lambda/python image, because
# AL2023's default repositories no longer ship LibreOffice.
FROM python:3.12-slim-bookworm

# LibreOffice + Poppler + Japanese fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress \
      poppler-utils \
      fonts-noto-cjk \
      fontconfig \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Warm up LibreOffice profile to reduce cold-start
RUN soffice --headless --convert-to pdf /dev/null 2>/dev/null || true

# AWS Lambda Runtime Interface Client — required on non-Amazon-Linux bases
RUN pip install --no-cache-dir awslambdaric

# Place app under Lambda's standard task root
WORKDIR /var/task

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source into a `render/` package, not flat into /var/task,
# so handler.py's `from .layout_renderer import ...` relative imports
# resolve. A flat layout makes Lambda import handler as a top-level
# module, which has no parent package, and every invocation dies with
# Runtime.ImportModuleError.
COPY . ./render/

ENV PYTHONPATH=/var/task
ENV LOG_LEVEL=INFO

# Standard Lambda container entrypoint for custom base images:
# awslambdaric consumes the handler spec passed as CMD.
ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["render.handler.handler"]
