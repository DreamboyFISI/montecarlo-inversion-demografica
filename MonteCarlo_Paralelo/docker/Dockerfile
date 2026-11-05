# Imagen para compilar y ejecutar las versiones secuencial, OpenMP y MPI.
# Contexto de construccion: la raiz del repositorio (lo hace docker-compose.yml).
#   docker build -f MonteCarlo_Paralelo/docker/Dockerfile -t montecarlo-demografia .
# La misma imagen sirve de nodo del cluster MPI: todos los nodos comparten la clave SSH del usuario
# mpi, generada al construir la imagen (adecuado para un laboratorio, no para produccion).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        g++ make openmpi-bin libopenmpi-dev openssh-server openssh-client \
        python3 python3-matplotlib iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /run/sshd

# Usuario sin privilegios para mpirun (UID 1000, como el usuario habitual del anfitrion, para que
# pueda escribir en el volumen de resultados); SSH sin contrasena entre nodos.
RUN (userdel -r ubuntu 2>/dev/null || true) \
 && useradd -m -u 1000 -s /bin/bash mpi \
 && mkdir -p /home/mpi/.ssh \
 && ssh-keygen -q -t ed25519 -N "" -f /home/mpi/.ssh/id_ed25519 \
 && cp /home/mpi/.ssh/id_ed25519.pub /home/mpi/.ssh/authorized_keys \
 && printf "Host *\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n  LogLevel ERROR\n" > /home/mpi/.ssh/config \
 && chmod 700 /home/mpi/.ssh && chmod 600 /home/mpi/.ssh/* \
 && chown -R mpi:mpi /home/mpi/.ssh

# OpenMPI dentro de contenedores: sin CMA (ptrace restringido) y TCP solo por la red del cluster.
ENV OMPI_MCA_btl_vader_single_copy_mechanism=none \
    OMPI_MCA_btl_tcp_if_include=eth0 \
    OMPI_MCA_oob_tcp_if_include=eth0

WORKDIR /home/mpi/proyecto
COPY --chown=mpi:mpi MonteCarlo_Secuencial/src MonteCarlo_Secuencial/src
COPY --chown=mpi:mpi MonteCarlo_Secuencial/datos MonteCarlo_Secuencial/datos
COPY --chown=mpi:mpi MonteCarlo_Secuencial/Makefile MonteCarlo_Secuencial/*.ini MonteCarlo_Secuencial/
COPY --chown=mpi:mpi MonteCarlo_Paralelo/src MonteCarlo_Paralelo/src
COPY --chown=mpi:mpi MonteCarlo_Paralelo/scripts MonteCarlo_Paralelo/scripts
COPY --chown=mpi:mpi MonteCarlo_Paralelo/Makefile MonteCarlo_Paralelo/hostfile MonteCarlo_Paralelo/

USER mpi
RUN make -C MonteCarlo_Paralelo all secuencial \
 && MonteCarlo_Secuencial/simulador --self-test --datos MonteCarlo_Secuencial/datos > /dev/null
WORKDIR /home/mpi/proyecto/MonteCarlo_Paralelo

# Por defecto el contenedor es un nodo del cluster: queda escuchando SSH (requiere root).
USER root
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
