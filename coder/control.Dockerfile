FROM python:3.15.2-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd
RUN useradd --create-home --uid 1000 --shell /bin/bash coder
COPY coder /usr/bin/coder
USER coder
WORKDIR /home/coder
ENTRYPOINT ["/usr/bin/coder"]
CMD ["server"]
