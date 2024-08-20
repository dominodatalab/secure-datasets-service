tag=${1}
operator_image="${operator_image:-quay.io/domino/secure-ds-service}"
#docker build -f ./Dockerfile -t ${operator_image}:${tag} .
docker build --platform=linux/amd64 -f ./Dockerfile -t ${operator_image}:${tag} .
docker push ${operator_image}:${tag}