FROM codercom/code-server:4.144.0@sha256:b9e8056bb74bd0c4f90284c7559eddeccd38400cfedc28e64c9d3ca50fef1f83 AS editor
FROM python:3.15.2-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd
ARG CODE_SERVER_VERSION=4.144.0
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git sudo procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 coder
COPY --from=editor /usr/lib/code-server /usr/lib/code-server
RUN ln -s /usr/lib/code-server/bin/code-server /usr/local/bin/code-server
COPY --chown=coder:coder starter/ /opt/orderdesk-seed/
USER coder
WORKDIR /home/coder
ENV SHELL=/bin/bash
