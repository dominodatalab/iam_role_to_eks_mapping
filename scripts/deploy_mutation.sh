image="${image:-quay.io/domino/iam-sa-mapping-client}"
platform_namespace="${platform_namespace:-domino-platform}"

VERSION=$1
mutation='aws-iam-to-sa-mapping'
echo $image
echo $VERSION
kubectl delete mutation $mutation -n $platform_namespace

cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: apps.dominodatalab.com/v1alpha1
kind: Mutation
metadata:
  name: ${mutation}
rules:
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  modifySecurityContext:
    context:
      fsGroup: 12574
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  insertContainer:
    containerType: app
    spec:
      image: ${image}:${VERSION}
      name: aws-config-file-generator
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  insertVolumeMounts:
    containerSelector:
    - aws-config-file-generator
    volumeMounts:
    - name: jwt-secret-vol
      mountPath: /var/lib/domino/home/.api
      readOnly: true
    - name: podinfo
      mountPath: /var/run/podinfo
      readOnly: true
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  insertVolumes:
  - name: aws-config-file
    emptyDir:
      sizeLimit: 500Mi
  - name: podinfo
    downwardAPI:
      items:
        - path: "labels"
          fieldRef:
            fieldPath: metadata.labels
  - name: aws-user-token
    projected:
      defaultMode: 422
      sources:
      - serviceAccountToken:
          path: token
          expirationSeconds: 86400
          audience: sts.amazonaws.com
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  insertVolumeMounts:
    containerSelector:
    - run
    volumeMounts:
    - name: aws-config-file
      mountPath: /var/run/.aws
    - name: aws-user-token
      mountPath: /var/run/secrets/eks.amazonaws.com/serviceaccount/
      readOnly: true
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  insertVolumeMounts:
    containerSelector:
    - aws-config-file-generator
    volumeMounts:
    - name: aws-config-file
      mountPath: /var/run/.aws
    - name: aws-user-token
      mountPath: /var/run/secrets/eks.amazonaws.com/serviceaccount/
      readOnly: true
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  modifyEnv:
    containerSelector:
    - aws-config-file-generator
    env:
    - name: POD_INFO_PATH
      value: /var/run/podinfo/labels
    - name: DOMINO_TOKEN_FILE
      value: /var/lib/domino/home/.api/token
- labelSelectors:
  - "dominodatalab.com/workload-type in (Workspace,Job)"
  modifyEnv:
    containerSelector:
    - run
    - aws-config-file-generator
    env:
    - name: AWS_WEB_IDENTITY_TOKEN_FILE
      value: /var/run/secrets/eks.amazonaws.com/serviceaccount/token
    - name: AWS_CONFIG_FILE
      value: /var/run/.aws/config
    - name: IAM_SA_MAPPING_ENDPOINT
      value: http://iam-sa-mapping-svc.domino-platform/map_iam_role_to_pod_sa
EOF