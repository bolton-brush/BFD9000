FROM docker.io/python:3.12-slim

WORKDIR /app

COPY mock_bfd9010.py .
COPY sample_images.bz2 .

# Decompress sample images into /app/sample_images/
RUN apt-get update && apt-get install -y --no-install-recommends bzip2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p sample_images \
    && tar -xjf sample_images.bz2 -C sample_images --strip-components=1 \
    && rm sample_images.bz2

EXPOSE 9010

CMD ["python", "mock_bfd9010.py", "--host", "0.0.0.0", "--port", "9010"]
