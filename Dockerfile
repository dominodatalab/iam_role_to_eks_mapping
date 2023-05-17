FROM quay.io/domino/python-public:3.8.7-slim
RUN apt-get update && apt-get upgrade -y
ADD requirements.txt .
ENV PATH=$PATH:/app/.local/bin:/app/bin
ENV PYTHONUNBUFFERED=true
ENV PYTHONUSERBASE=/home/app
ENV PYTHONPATH=/
ENV FLASK_ENV=production
ENV LOG_LEVEL=DEBUG
RUN pip install --upgrade pip
RUN ls
RUN pip install --user -r requirements.txt
ADD iam_to_sa_mapping /iam_to_sa_mapping
ENTRYPOINT ["python",  "/iam_to_sa_mapping/iam_to_sa_service.py"]
