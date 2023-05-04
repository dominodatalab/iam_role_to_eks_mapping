platform_namespace="${platform_namespace:-domino-platform}"
asset_aws_account=$1
eks_aws_account=$2
role_prefix=$3

kubectl delete configmap domino-org-iamrole-mapping -n ${platform_namespace}
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: domino-org-iamrole-mapping
data: {
    "iamrole-list-bucket":"arn:aws:iam::${asset_aws_account}:role/${role_prefix}list-bucket-role",
    "iamrole-read-bucket":"arn:aws:iam::${asset_aws_account}:role/${role_prefix}read-bucket-role",
    "iamrole-update-bucket":"arn:aws:iam::${asset_aws_account}:role/${role_prefix}update-bucket-role"
  }
EOF

kubectl delete configmap resource-role-to-eks-role-mapping -n ${platform_namespace}
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: resource-role-to-eks-role-mapping
data: {
  "${role_prefix}list-bucket-role":"arn:aws:iam::${eks_aws_account}:role/${role_prefix}list-bucket-role",
  "${role_prefix}read-bucket-role":"arn:aws:iam::${eks_aws_account}:role/${role_prefix}read-bucket-role",
  "${role_prefix}update-bucket-role":"arn:aws:iam::${eks_aws_account}:role/${role_prefix}update-bucket-role"
}
EOF