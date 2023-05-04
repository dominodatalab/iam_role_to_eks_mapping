import json
from threading import RLock
from kubernetes import client, config
from kubernetes.client import V1ObjectMeta, V1PodList

import boto3
from kubernetes.client.models.v1_config_map import V1ConfigMap
import requests
import os
import certifi

DEFAULT_PLATFORM_NS = "domino-platform"
DEFAULT_COMPUTE_NS = "domino-compute"
CONFIG_MAP_ORG_TO_IAMROLE_MAPPING = "domino-org-iamrole-mapping"
CONFIG_MAP_RESOURCE_ROLE_TO_EKS_ROLE_MAPPING = "resource-role-to-eks-role-mapping"


class AWSUtils:
    def __init__(self, logger):
        try:
            self.lock = RLock()
            self._iam = boto3.client("iam")
            self._logger = logger
            self._all_running_svc_accounts = []
            config.load_incluster_config()
        except:
            print("Loading local k8s config")
            config.load_kube_config()

    def get_resource_role_to_eks_role_mapping(self, platform_ns: DEFAULT_PLATFORM_NS):
        v1 = client.CoreV1Api()
        resource_role_to_eks_role_mapping: V1ConfigMap = v1.read_namespaced_config_map(
            CONFIG_MAP_RESOURCE_ROLE_TO_EKS_ROLE_MAPPING, platform_ns
        )
        return resource_role_to_eks_role_mapping.data

    def get_domino_users_iamroles(self, platform_ns: DEFAULT_PLATFORM_NS, headers):
        user_orgs = self.get_user_orgs(headers)
        orgs_to_iam_roles_map = self.get_orgs_iam_roles_mapping(platform_ns)
        my_roles = {}
        for org in user_orgs:
            if org in orgs_to_iam_roles_map:
                my_roles[org] = orgs_to_iam_roles_map[org]
        return my_roles

    def get_role_arn_by_role_name_map(self, role_arns):
        rolearns_by_name = {}
        for arn in role_arns:
            role_name = arn[arn.index("/") + 1 :]
            rolearns_by_name[role_name] = arn
        return rolearns_by_name

    def get_orgs_iam_roles_mapping(self, platform_ns: DEFAULT_PLATFORM_NS):
        v1 = client.CoreV1Api()
        org_gcp_svc_mapping: V1ConfigMap = v1.read_namespaced_config_map(
            CONFIG_MAP_ORG_TO_IAMROLE_MAPPING, platform_ns
        )
        return org_gcp_svc_mapping.data

    def _patch_config_map(
        self, namespace: str, config_map_name: str, config_map_body: dict
    ):
        v1 = client.CoreV1Api()
        config_map: V1ConfigMap = v1.read_namespaced_config_map(
            config_map_name, namespace
        )
        """
        metadata: V1ObjectMeta = config_map.metadata
        resource_version = int(metadata.resource_version)
        metadata.resource_version = str(resource_version + 1)
        """

        v1.patch_namespaced_config_map(config_map_name, namespace, config_map_body)

    def update_orgs_iam_roles_mapping(
        self, domino_org, iam_role, platform_ns: DEFAULT_PLATFORM_NS
    ):
        try:
            config.load_incluster_config()
        except:
            print("Loading local k8s config")
            config.load_kube_config()
        v1 = client.CoreV1Api()
        org_iam_role_mapping: V1ConfigMap = v1.read_namespaced_config_map(
            CONFIG_MAP_ORG_TO_IAMROLE_MAPPING, platform_ns
        )

        if not org_iam_role_mapping.data:
            org_iam_role_mapping.data = {}

        old_iam_role = ""

        if domino_org in org_iam_role_mapping.data:
            old_iam_role = org_iam_role_mapping.data[domino_org]

        org_iam_role_mapping.data[domino_org] = iam_role

        v1.patch_namespaced_config_map(
            CONFIG_MAP_ORG_TO_IAMROLE_MAPPING, platform_ns, org_iam_role_mapping
        )
        # self._patch_config_map(platform_ns, CONFIG_MAP_ORG_TO_IAMROLE_MAPPING,
        #                 org_iam_role_mapping.data)
        return old_iam_role, iam_role

    def get_user_id(self, headers):
        domino_host = os.environ.get(
            "DOMINO_USER_HOST", "http://nucleus-frontend.domino-platform:80"
        )

        endpoint = f"{domino_host}/v4/auth/principal"

        resp = requests.get(endpoint, headers=headers)

        if resp.status_code == 200:
            return resp.json()["canonicalId"]

    def get_user_orgs(self, headers):

        domino_host = os.environ.get(
            "DOMINO_USER_HOST", "http://nucleus-frontend.domino-platform:80"
        )

        url = f"{domino_host}/v4/organizations/self"
        resp = requests.get(url, headers=headers)
        lst = []

        if resp.status_code == 200:
            for org in resp.json():
                lst.append(org["name"])

        return lst

    def get_user_roles(self, headers):
        domino_host = os.environ.get(
            "DOMINO_USER_HOST", "http://nucleus-frontend.domino-platform:80"
        )

        url = f"{domino_host}/api/organizations/v1/organizations"

        resp = requests.get(url, headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            lst = []
            for o in data["orgs"]:
                lst.append(o["name"])
        return lst

    def is_user_admin(self, headers):
        domino_host = os.environ.get(
            "DOMINO_USER_HOST", "http://nucleus-frontend.domino-platform:80"
        )
        url = f"{domino_host}/v4/auth/principal"

        resp = requests.get(url, headers=headers)

        if resp.status_code == 200:
            return resp.json()["isAdmin"]

    def _is_service_account_mapped(self, trust_policy, service_account, oidc_provider):
        print(trust_policy["Statement"][0]["Condition"])
        print(
            trust_policy["Statement"][0]["Condition"]["StringLike"][
                f"{oidc_provider}:sub"
            ]
        )
        return (
            service_account
            in trust_policy["Statement"][0]["Condition"]["StringLike"][
                f"{oidc_provider}:sub"
            ]
        )

    def map_iam_roles_to_pod(
        self, platform_ns, oidc_provider_arn, role_names, pod_svc_account
    ):
        # service_account = f"*:{compute_ns}:{pod_svc_account}"
        with self.lock:
            service_account = "*" + pod_svc_account[4:]

            resource_role_to_eks_role_mapping = (
                self.get_resource_role_to_eks_role_mapping(platform_ns)
            )
            for role_name in role_names:
                eks_arn = resource_role_to_eks_role_mapping[role_name]
                eks_role_name = eks_arn[eks_arn.index("/") + 1 :]

                response = self._iam.get_role(RoleName=eks_role_name)
                trust_policy = response["Role"]["AssumeRolePolicyDocument"]

                oidc_provider = oidc_provider_arn

                if not self._is_service_account_mapped(
                    trust_policy, service_account, oidc_provider
                ):
                    if (
                        type(
                            trust_policy["Statement"][0]["Condition"]["StringLike"][
                                f"{oidc_provider}:sub"
                            ]
                        )
                        == str
                    ):
                        v = trust_policy["Statement"][0]["Condition"]["StringLike"][
                            f"{oidc_provider}:sub"
                        ]
                        if v[1:] in self._all_running_svc_accounts:
                            lst = [v, service_account]
                        else:
                            lst = [service_account]

                        trust_policy["Statement"][0]["Condition"]["StringLike"][
                            f"{oidc_provider}:sub"
                        ] = lst
                    else:
                        sub_list = trust_policy["Statement"][0]["Condition"][
                            "StringLike"
                        ][f"{oidc_provider}:sub"]
                        new_sub_list = []
                        new_sub_list.append(service_account)
                        for s in sub_list:
                            if s[1:] in self._all_running_svc_accounts:
                                new_sub_list.append(s)
                        trust_policy["Statement"][0]["Condition"]["StringLike"][
                            f"{oidc_provider}:sub"
                        ] = new_sub_list

                    self._iam.update_assume_role_policy(
                        RoleName=eks_role_name, PolicyDocument=json.dumps(trust_policy)
                    )
                else:
                    print("already there")

    def get_pod_service_account(
        self, headers, run_id, pod_namespace=DEFAULT_COMPUTE_NS
    ):
        user_id = self.get_user_id(headers)
        self._all_running_svc_accounts = []
        try:
            config.load_incluster_config()
        except:
            print("Loading local k8s config")
            config.load_kube_config()
        v1 = client.CoreV1Api()
        podLst: V1PodList = v1.list_namespaced_pod(pod_namespace)

        for p in podLst.items:
            pod: V1PodList = p
            m: V1ObjectMeta = pod.metadata
            metadata = m.to_dict()
            if pod.status.phase.lower() == "running":
                self._all_running_svc_accounts.append(pod.spec.service_account[4:])
            if (
                metadata["labels"]
                and "dominodatalab.com/execution-id" in metadata["labels"].keys()
            ):
                execution_id = metadata["labels"]["dominodatalab.com/execution-id"]
                if execution_id == run_id:
                    pod_user_id = metadata["labels"][
                        "dominodatalab.com/starting-user-id"
                    ]
                    if pod_user_id == user_id:
                        return p.spec.service_account
        return None
