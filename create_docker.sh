docker build --tag docker-oruxmaps .
mkdir -p target
docker run --rm -v `pwd`/target:/orux_swisstopo/target -it docker-oruxmaps
