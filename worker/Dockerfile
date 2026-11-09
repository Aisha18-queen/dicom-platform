# Dummy worker image. The ML teammate builds the real images (one for the liver CT
# with PyTorch/MONAI, one for the brain MRI with TensorFlow/Keras) on the same pattern.
FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /code/worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
