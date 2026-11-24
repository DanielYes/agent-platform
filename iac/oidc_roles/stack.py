"""Proveedor OIDC de GitHub y un rol IAM de mínimo privilegio por agente.

Nada de este archivo contiene cuentas ni repositorios: todo llega como parámetros
(contexto de CDK) desde app.py.
"""

from dataclasses import dataclass, field

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_AUDIENCE = "sts.amazonaws.com"

ALL_ROLES = (
    "infra-readonly",
    "cicd-deployer",
    "observabilidad-logs",
    "costos-billing",
    "seguridad-audit",
)


@dataclass(frozen=True)
class OidcRolesConfig:
    github_owner: str
    github_repos: list[str]
    roles: list[str] = field(default_factory=lambda: list(ALL_ROLES))
    oidc_provider_arn: str | None = None
    default_branch: str = "main"
    deploy_environments: list[str] = field(default_factory=lambda: ["staging"])
    cdk_qualifier: str = "hnb659fds"
    infra_readonly_mode: str = "cdk"  # cdk | terraform
    tf_state_bucket: str | None = None
    log_group_prefix: str = ""
    role_name_prefix: str = "agent-platform"

    def __post_init__(self) -> None:
        if not self.github_owner or not self.github_repos:
            raise ValueError("github_owner y github_repos son obligatorios.")
        unknown = set(self.roles) - set(ALL_ROLES)
        if unknown:
            raise ValueError(f"Roles desconocidos: {sorted(unknown)}. Válidos: {ALL_ROLES}")
        if self.infra_readonly_mode not in ("cdk", "terraform"):
            raise ValueError("infra_readonly_mode debe ser 'cdk' o 'terraform'.")


class OidcRolesStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, config: OidcRolesConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config

        if config.oidc_provider_arn:
            provider_arn = config.oidc_provider_arn
        else:
            provider = iam.CfnOIDCProvider(
                self,
                "GitHubOidcProvider",
                url=GITHUB_OIDC_URL,
                client_id_list=[GITHUB_OIDC_AUDIENCE],
            )
            provider_arn = provider.attr_arn
        self.provider_arn = provider_arn

        builders = {
            "infra-readonly": self._infra_readonly,
            "cicd-deployer": self._cicd_deployer,
            "observabilidad-logs": self._observabilidad_logs,
            "costos-billing": self._costos_billing,
            "seguridad-audit": self._seguridad_audit,
        }
        for name in config.roles:
            role = builders[name]()
            CfnOutput(self, f"{_pascal(name)}RoleArn", value=role.role_arn)

    # --- Confianza -------------------------------------------------------

    def _subjects(self, suffix: str) -> list[str]:
        return [f"repo:{self.config.github_owner}/{repo}:{suffix}" for repo in self.config.github_repos]

    def _role(self, name: str, description: str, subjects: list[str]) -> iam.Role:
        principal = iam.FederatedPrincipal(
            self.provider_arn,
            conditions={
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": GITHUB_OIDC_AUDIENCE,
                    "token.actions.githubusercontent.com:sub": subjects,
                },
            },
            assume_role_action="sts:AssumeRoleWithWebIdentity",
        )
        return iam.Role(
            self,
            _pascal(name),
            role_name=f"{self.config.role_name_prefix}-{name}",
            description=description,
            assumed_by=principal,
            max_session_duration=Duration.hours(1),
        )

    # --- Roles -----------------------------------------------------------

    def _infra_readonly(self) -> iam.Role:
        """cdk diff / terraform plan en PRs. Nunca puede desplegar."""
        role = self._role(
            "infra-readonly",
            "agent-platform: cdk diff / terraform plan en PRs (solo lectura).",
            self._subjects("pull_request"),
        )
        if self.config.infra_readonly_mode == "cdk":
            q = self.config.cdk_qualifier
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="AssumeCdkLookupRole",
                    actions=["sts:AssumeRole"],
                    resources=[f"arn:{self.partition}:iam::{self.account}:role/cdk-{q}-lookup-role-*"],
                )
            )
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="ReadCloudFormation",
                    actions=[
                        "cloudformation:DescribeStacks",
                        "cloudformation:DescribeStackResources",
                        "cloudformation:GetTemplate",
                        "cloudformation:GetTemplateSummary",
                        "cloudformation:ListStacks",
                        "cloudformation:ListStackResources",
                    ],
                    resources=["*"],
                )
            )
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="ReadCdkBootstrapVersion",
                    actions=["ssm:GetParameter"],
                    resources=[f"arn:{self.partition}:ssm:*:{self.account}:parameter/cdk-bootstrap/{q}/*"],
                )
            )
        else:
            # Terraform necesita leer la configuración de cualquier recurso que gestione.
            role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("ReadOnlyAccess"))
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="DenyDataPlaneReads",
                    effect=iam.Effect.DENY,
                    actions=[
                        "secretsmanager:GetSecretValue",
                        "dynamodb:GetItem",
                        "dynamodb:BatchGetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                    ],
                    resources=["*"],
                )
            )
            state_bucket = self.config.tf_state_bucket
            deny_s3 = iam.PolicyStatement(
                sid="DenyS3ObjectReadsExceptState",
                effect=iam.Effect.DENY,
                actions=["s3:GetObject", "s3:GetObjectVersion"],
            )
            if state_bucket:
                deny_s3.add_not_resources(f"arn:{self.partition}:s3:::{state_bucket}/*")
            else:
                deny_s3.add_resources("*")
            role.add_to_policy(deny_s3)
        return role

    def _cicd_deployer(self) -> iam.Role:
        """Despliegue con CDK: solo puede asumir los roles del bootstrap de CDK."""
        role = self._role(
            "cicd-deployer",
            "agent-platform: despliegue desde environments protegidos de GitHub.",
            [s for env in self.config.deploy_environments for s in self._subjects(f"environment:{env}")],
        )
        q = self.config.cdk_qualifier
        role.add_to_policy(
            iam.PolicyStatement(
                sid="AssumeCdkBootstrapRoles",
                actions=["sts:AssumeRole", "sts:TagSession"],
                resources=[
                    f"arn:{self.partition}:iam::{self.account}:role/cdk-{q}-{kind}-role-*"
                    for kind in ("deploy", "file-publishing", "image-publishing", "lookup")
                ],
            )
        )
        return role

    def _observabilidad_logs(self) -> iam.Role:
        role = self._role(
            "observabilidad-logs",
            "agent-platform: lectura de alarmas, métricas y logs de CloudWatch.",
            self._subjects(f"ref:refs/heads/{self.config.default_branch}"),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadCloudWatch",
                actions=[
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:DescribeAlarmHistory",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics",
                    "logs:DescribeLogGroups",
                    "logs:GetQueryResults",
                    "logs:StopQuery",
                ],
                resources=["*"],
            )
        )
        prefix = self.config.log_group_prefix
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadLogGroups",
                actions=["logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams", "logs:StartQuery"],
                resources=[f"arn:{self.partition}:logs:*:{self.account}:log-group:{prefix}*"],
            )
        )
        return role

    def _costos_billing(self) -> iam.Role:
        role = self._role(
            "costos-billing",
            "agent-platform: lectura de Cost Explorer, presupuestos y precios.",
            self._subjects(f"ref:refs/heads/{self.config.default_branch}"),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ReadCosts",
                actions=[
                    "ce:GetCostAndUsage",
                    "ce:GetCostForecast",
                    "ce:GetDimensionValues",
                    "budgets:ViewBudget",
                    "pricing:DescribeServices",
                    "pricing:GetAttributeValues",
                    "pricing:GetProducts",
                ],
                resources=["*"],
            )
        )
        return role

    def _seguridad_audit(self) -> iam.Role:
        role = self._role(
            "seguridad-audit",
            "agent-platform: auditoría de seguridad de solo lectura (IAM y configuración).",
            self._subjects(f"ref:refs/heads/{self.config.default_branch}"),
        )
        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("SecurityAudit"))
        return role


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))
