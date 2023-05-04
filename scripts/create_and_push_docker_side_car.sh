set -e
tag="${tag:-latest}"
operator_image="${operator_image:-quay.io/domino/iam-sa-mapping-client}"
docker build -f ./AWSConfigServiceDockerfile -t ${operator_image}:${tag} .
docker push ${operator_image}:${tag}