platform_namespace="${platform_namespace:-domino-platform}"
asset_aws_account=$1
eks_aws_account=$2

kubectl delete configmap domino-org-iamrole-mapping -n ${platform_namespace}
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: domino-org-iamrole-mapping
data: {
    "iamrole-list-bucket":"arn:aws:iam::${asset_aws_account}:role/list-bucket-role",
    "iamrole-read-bucket":"arn:aws:iam::${asset_aws_account}:role/read-bucket-role",
    "iamrole-update-bucket":"arn:aws:iam::${asset_aws_account}:role/update-bucket-role"
  }
EOF

kubectl delete configmap resource-role-to-eks-role-mapping -n ${platform_namespace}
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: resource-role-to-eks-role-mapping
data: {
  "list-bucket-role":"arn:aws:iam::${eks_aws_account}:role/list-bucket-role",
  "read-bucket-role":"arn:aws:iam::${eks_aws_account}:role/read-bucket-role",
  "update-bucket-role":"arn:aws:iam::${eks_aws_account}:role/update-bucket-role"
}
EOF