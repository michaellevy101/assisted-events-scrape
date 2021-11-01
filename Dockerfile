FROM quay.io/ocpmetal/assisted-service:latest AS service

FROM quay.io/centos/centos:stream8
RUN dnf update -y && dnf install -y python3 python3-pip && dnf clean all && python3 -m pip install --upgrade pip
WORKDIR assisted_event_scrap/
ADD .  ./
COPY --from=service /clients/assisted-service-client-*.tar.gz /build/pip/
RUN python3 -m pip install -r requirements.txt && python3 -m pip install --upgrade /build/pip/* && rm -rf build/
