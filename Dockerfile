FROM fedora:27

ENV VERSION master

EXPOSE 8181

RUN dnf -y install tar libvirt-python3 && dnf clean all

RUN dnf -y install python3-greenlet \
           python3-gevent \
           python3-devel \
           gcc \
           redhat-rpm-config && \
    dnf clean all


LABEL io.cadvisor.metric.prometheus-vadvisor="/var/vadvisor/cadvisor_config.json"

RUN \
    curl -LO https://github.com/bpradipt/vAdvisor/archive/$VERSION.tar.gz#/vAdvisor-$VERSION.tar.gz && \
    tar xf vAdvisor-$VERSION.tar.gz && cd vAdvisor-$VERSION && \
    sed -i '/libvirt-python/d' requirements.txt && \
    sed -i '/\<gevent\>/d' requirements.txt && \
    pip3 --no-cache-dir install -r requirements.txt && pip3 --no-cache-dir install . && \
    mkdir -p /var/vadvisor && cp docker/cadvisor_config.json /var/vadvisor/ && \
    cp docker/entrypoint.sh / && \
    rm -rf ~/.pip && \
    cd .. && rm -rf vAdvisor-$VERSION*

RUN cp /usr/local/bin/vAdvisor /usr/bin

ENTRYPOINT [ "/bin/bash", "/entrypoint.sh" ]
