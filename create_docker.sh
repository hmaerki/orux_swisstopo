docker build --tag docker-oruxmaps .
docker run -v `pwd`/target:/orux_swisstopo/target -it docker-oruxmaps
