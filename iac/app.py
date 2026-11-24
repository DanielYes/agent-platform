#!/usr/bin/env python3
"""App de CDK: proveedor OIDC de GitHub + roles por agente.

Todos los parámetros llegan por contexto (-c clave=valor). Ejemplo:

    cdk synth \
      -c github_owner=<OWNER> \
      -c github_repos=<REPO_1>,<REPO_2> \
      -c deploy_environments=staging

La cuenta y la región salen de las credenciales activas (CDK_DEFAULT_ACCOUNT /
CDK_DEFAULT_REGION) o de -c account=<ACCOUNT_ID> -c region=<REGION>.
"""

import os

import aws_cdk as cdk

from oidc_roles.stack import ALL_ROLES, OidcRolesConfig, OidcRolesStack


def _list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


app = cdk.App()
ctx = app.node.try_get_context

config = OidcRolesConfig(
    github_owner=ctx("github_owner") or "",
    github_repos=_list(ctx("github_repos")),
    roles=_list(ctx("roles")) or list(ALL_ROLES),
    oidc_provider_arn=ctx("oidc_provider_arn") or None,
    default_branch=ctx("default_branch") or "main",
    deploy_environments=_list(ctx("deploy_environments")) or ["staging"],
    cdk_qualifier=ctx("cdk_qualifier") or "hnb659fds",
    infra_readonly_mode=ctx("infra_readonly_mode") or "cdk",
    tf_state_bucket=ctx("tf_state_bucket") or None,
    log_group_prefix=ctx("log_group_prefix") or "",
    role_name_prefix=ctx("role_name_prefix") or "agent-platform",
)

OidcRolesStack(
    app,
    ctx("stack_name") or "AgentPlatformOidc",
    config=config,
    env=cdk.Environment(
        account=ctx("account") or os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=ctx("region") or os.environ.get("CDK_DEFAULT_REGION"),
    ),
    description="agent-platform: proveedor OIDC de GitHub y roles de mínimo privilegio por agente.",
)

app.synth()
