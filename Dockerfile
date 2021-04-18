FROM python:3.9-slim-buster

WORKDIR /orux_swisstopo

COPY requirements.txt requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

COPY . .

CMD [ "/bin/bash"]
