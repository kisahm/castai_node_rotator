
FROM python:3.11

ENV PATH /usr/local/bin:$PATH

ENV PYTHONUNBUFFERED 1

RUN mkdir /app
COPY /src /app
WORKDIR /app

# RUN apt-get update && \
#   apt-get install -y apt-transport-https ca-certificates curl gnupg && \
#   curl -fsSLo /usr/share/keyrings/kubernetes-archive-keyring.gpg https://packages.cloud.google.com/apt/doc/apt-key.gpg && \
#   echo “deb [signed-by=/usr/share/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main” | tee /etc/apt/sources.list.d/kubernetes.list && \
#   apt-get update && \
#   apt-get install -y kubectl && \
#   apt-get clean && \
#   rm -rf /var/lib/apt/lists/*

RUN curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
RUN chmod +x ./kubectl
RUN mv ./kubectl /usr/local/bin
RUN pip3 install -r requirements.txt

CMD ["python", "src.py"]