# iac: OIDC de GitHub y roles por agente

Stack de CDK en Python que crea, en **una cuenta de AWS**, el proveedor OIDC de GitHub y un rol IAM de mínimo privilegio por agente. Despliégalo una vez por cuenta (por ejemplo, staging y producción).

| Rol | Lo usa | Quién puede asumirlo (`sub` del token OIDC) | Permisos |
|---|---|---|---|
| `agent-platform-infra-readonly` | `on-pr-infra` | `repo:<OWNER>/<REPO>:pull_request` | Modo `cdk`: asumir el rol *lookup* del bootstrap de CDK y leer CloudFormation. Modo `terraform`: `ReadOnlyAccess` con denegación de lecturas de datos (secretos, ítems de DynamoDB y objetos de S3 salvo el bucket de estado). |
| `agent-platform-cicd-deployer` | `deploy-aws` | `repo:<OWNER>/<REPO>:environment:<ENV>` | Solo asumir los roles del bootstrap de CDK (`deploy`, `file-publishing`, `image-publishing`, `lookup`). |
| `agent-platform-observabilidad-logs` | `scheduled-weekly` | `repo:<OWNER>/<REPO>:ref:refs/heads/main` | Leer alarmas, métricas y logs (filtrables por prefijo de log group). |
| `agent-platform-costos-billing` | `scheduled-weekly` | `repo:<OWNER>/<REPO>:ref:refs/heads/main` | Leer Cost Explorer, presupuestos y precios. |
| `agent-platform-seguridad-audit` | `scheduled-weekly` | `repo:<OWNER>/<REPO>:ref:refs/heads/main` | Política administrada `SecurityAudit`. |

Todos los roles tienen sesiones de 1 hora como máximo.

## Parámetros (contexto de CDK)

| Clave | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `github_owner` | sí | | Usuario u organización de GitHub. |
| `github_repos` | sí | | Repositorios separados por comas. |
| `roles` | no | los 5 | Subconjunto de roles que se crean, separados por comas. |
| `oidc_provider_arn` | no | | ARN de un proveedor OIDC existente. Si se omite, se crea uno (solo puede haber uno por cuenta). |
| `deploy_environments` | no | `staging` | Environments de GitHub que pueden asumir `cicd-deployer`. |
| `default_branch` | no | `main` | Rama desde la que corren los workflows programados. |
| `cdk_qualifier` | no | `hnb659fds` | Qualifier del bootstrap de CDK. |
| `infra_readonly_mode` | no | `cdk` | `cdk` o `terraform`. |
| `tf_state_bucket` | no | | Bucket del estado de Terraform (modo `terraform`). |
| `log_group_prefix` | no | (todos) | Prefijo de log groups que puede leer `observabilidad-logs`. |
| `role_name_prefix` | no | `agent-platform` | Prefijo de los nombres de rol. |
| `stack_name` | no | `AgentPlatformOidc` | Nombre del stack. |
| `account`, `region` | no | credenciales activas | Cuenta y región de destino. |

## Uso

```bash
cd iac
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Revisa lo que se va a crear
npx aws-cdk@2 synth -c github_owner=<OWNER> -c github_repos=<REPO>

# Despliega (requiere credenciales con permisos de IAM en la cuenta de destino)
npx aws-cdk@2 deploy --profile <PERFIL> \
  -c github_owner=<OWNER> -c github_repos=<REPO> -c deploy_environments=production
```

Los ARNs de los roles quedan como *outputs* del stack. Guárdalos como **variables** (no secretos) del repositorio del proyecto, por ejemplo `AWS_ROLE_ARN_INFRA_READONLY`.

## Notas

- `cicd-deployer` asume que el proyecto despliega con CDK y que la cuenta tiene `cdk bootstrap`. Para Terraform hay que darle al rol los permisos que gestione el proyecto.
- Cost Explorer solo tiene datos completos en la cuenta de administración (*payer*) de una organización.
- Si un proyecto usa `cdk diff` con recursos que requieren *lookups* (VPC, AMIs), el rol *lookup* del bootstrap ya cubre esas lecturas.
