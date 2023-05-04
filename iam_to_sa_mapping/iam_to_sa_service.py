from flask import Flask, request, Response  # type: ignore
import logging
import os
from iam_to_sa_mapping.aws_utils import AWSUtils

DEFAULT_PLATFORM_NS = "domino-platform"
DEFAULT_COMPUTE_NS = "domino-compute"
PLATFORM_NS = os.environ.get("PLATFORM_NS", DEFAULT_PLATFORM_NS)
COMPUTE_NS = os.environ.get("COMPUTE_NS", DEFAULT_COMPUTE_NS)
OIDC_PROVIDER = os.environ.get("OIDC_PROVIDER")
OIDC_PROVIDER_AUDIENCE = os.environ.get("OIDC_PROVIDER_AUDIENCE")

logger = logging.getLogger("iamroletosamapping")
app = Flask(__name__)

aws_utils: AWSUtils = AWSUtils(logger)


def get_domino_api_headers(headers):
    new_headers = {}
    if "Authorization" in headers:
        new_headers["Authorization"] = headers["Authorization"]
    elif "X-Domino-Api-Key" in headers:
        new_headers["X-Domino-Api-Key"] = headers["X-Domino-Api-Key"]
    return new_headers


# This implementation should be in a separate micro-service unique for each customer
# Default depends on org to roles mapping
@app.route("/get_my_roles", methods=["GET"])
def get_my_roles() -> tuple:
    headers = get_domino_api_headers(request.headers)
    platform_ns = os.environ.get("DEFAULT_PLATFORM_NS", DEFAULT_PLATFORM_NS)
    return {"result": aws_utils.get_domino_users_iamroles(platform_ns, headers)}


@app.route("/map_org_to_iam_role", methods=["POST"])
def map_org_to_iam_role() -> object:
    headers = get_domino_api_headers(request.headers)
    is_caller_admin = aws_utils.is_user_admin(get_domino_api_headers(headers))
    payload = request.json
    if not is_caller_admin:
        return Response(
            str("Not Authorized. Only a Domino Admin can map domino orgs to iam roles"),
            403,
        )
    if not ("domino_org" in payload and "iam_role" in payload):
        return Response(
            str("Pay load must contain attributes domino_org and iam_role"), 404
        )
    else:
        domino_org = payload["domino_org"]
        iam_role = payload["iam_role"]
        if not domino_org or not iam_role:
            return Response(
                str(
                    "Pay load must contain a non-empty domino org and a not-empty iam_role"
                ),
                404,
            )
        old_gcp_sa, new_gcp_sa = aws_utils.update_orgs_iam_roles_mapping(
            domino_org, iam_role, PLATFORM_NS
        )
        return Response(
            str(
                f"Domino Org {domino_org} mapping updated from IAM ROLE {old_gcp_sa} to {new_gcp_sa}"
            ),
            200,
        )


@app.route("/map_iam_role_to_pod_sa", methods=["POST"])
def map_iam_roles_to_aws_sa() -> list:
    """
    Returns a list of iam roles the user (pod SA) can assume
    Returns:
           list(str): List of fully qualified iam roles the user can assume
    """

    headers = get_domino_api_headers(request.headers)
    payload = request.json
    run_id = payload["run_id"]

    pod_svc_account = aws_utils.get_pod_service_account(headers, run_id, COMPUTE_NS)
    if not pod_svc_account:
        return Response(str(f"No Pod Found with the run id {run_id} for the user"), 404)
    aws_resource_roles: dict = aws_utils.get_domino_users_iamroles(PLATFORM_NS, headers)

    resource_role_to_eks_role_mapping = aws_utils.get_resource_role_to_eks_role_mapping(
        PLATFORM_NS
    )
    aws_resource_roles_by_name = aws_utils.get_role_arn_by_role_name_map(
        aws_resource_roles.values()
    )
    # Update trust relationship for the the eks role
    aws_utils.map_iam_roles_to_pod(
        PLATFORM_NS, OIDC_PROVIDER, aws_resource_roles_by_name, pod_svc_account
    )

    aws_config_file = ""

    for role in aws_resource_roles_by_name.keys():
        aws_config_file = aws_config_file + f"[profile {role}]\n"
        aws_config_file = aws_config_file + f"source_profile = src_{role}\n"
        aws_config_file = (
            aws_config_file + f"role_arn={aws_resource_roles_by_name[role]}\n"
        )

        aws_config_file = aws_config_file + f"[profile src_{role}]\n"
        aws_config_file = (
            aws_config_file
            + f"web_identity_token_file = /var/run/secrets/eks.amazonaws.com/serviceaccount/token\n"
        )
        aws_config_file = (
            aws_config_file + f"role_arn={resource_role_to_eks_role_mapping[role]}\n"
        )
    return aws_config_file


@app.route("/healthz")
def alive():
    return "{'status': 'Healthy'}"


if __name__ == "__main__":
    lvl: str = logging.getLevelName(os.environ.get("LOG_LEVEL", "DEBUG"))
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    debug: bool = os.environ.get("FLASK_ENV") == "development"
    ssl_off = os.environ.get("SSL_OFF", "true") == "true"
    port = 6000
    if ssl_off:
        logger.debug(f"Running only http on port {port}")
        app.run(
            host=os.environ.get("FLASK_HOST", "0.0.0.0"),
            port=6000,
            debug=debug,
        )
    else:
        logger.debug(f"Running on port {port}")
        app.run(
            host=os.environ.get("FLASK_HOST", "0.0.0.0"),
            port=6000,
            debug=debug,
            ssl_context=("/ssl/tls.crt", "/ssl/tls.key"),
        )
