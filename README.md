# agent-platform

Plataforma central de agentes de desarrollo para proyectos en **GitHub y AWS**, con backend en Python o Node y frontend web. El stack, los comandos y el framework de pruebas de cada proyecto los toman los agentes de su `AGENTS.md` (o `CLAUDE.md`).

**Principio:** agente = rol genérico (vive aquí) + contexto del proyecto (vive en el repositorio de cada proyecto). Este repositorio nunca contiene contexto de un proyecto concreto.

Incluye:

- **15 subagentes de Claude Code**, instalables como plugin desde este mismo repositorio (que también es un marketplace).
- **Workflows reutilizables** de GitHub Actions: CI de Python, escaneo de seguridad, despliegue a AWS con OIDC y workflows que disparan a los agentes.
- **IaC (CDK en Python)** para el proveedor OIDC de GitHub y un rol de mínimo privilegio por agente.
- **Plantillas** de `AGENTS.md` y `agents.yaml` para cada proyecto.
- **Fábrica de agentes** ([`fabrica/`](fabrica/README.md)): vista 3D en vivo de qué agente está trabajando, en qué proyecto y en qué máquina, más los issues, PRs y runs de los repos. Corre en un equipo de la red local; el hook que la alimenta viene con el plugin y está inactivo hasta que configuras `FABRICA_URL`.

## Agentes

Cada agente define su propósito, cuándo se activa, qué contexto del proyecto lee, qué puede y qué no puede hacer, y cuándo escala a un humano. Están en `agents/`, agrupados por fase (la fase también aparece en el cuerpo de cada agente). Al instalarse se llaman `agent-platform:<nombre>`.

| Fase | Agente | Para qué sirve | Lee del proyecto | Permisos clave |
|---|---|---|---|---|
| 00-orquestador | `tech-lead` | Clasifica issues y, como agente principal de la sesión, planea, delega y consolida un requerimiento | `agents.yaml`, `AGENTS.md`, issues abiertos | Asigna y delega; no escribe código |
| 00-orquestador | `onboarding` | Prepara un proyecto nuevo para usar la plataforma (se usa una vez) | todo el repo | Genera borradores de `AGENTS.md`, `agents.yaml` y `docs/` vía PR |
| 01-planificacion | `producto` | Convierte ideas en issues e historias de usuario con criterios de aceptación, en el formato del proyecto (p. ej. PDF) | `docs/producto.md`, sección "Historias de usuario" de `AGENTS.md` | Crea issues y documentos de historias; no toca código |
| 01-planificacion | `arquitecto` | Toma y documenta decisiones técnicas, y evalúa alternativas | `docs/arquitectura.md`, `docs/adr/` | Escribe ADRs y revisa PRs grandes |
| 02-construccion | `desarrollador-backend` | Implementa APIs, Lambdas y lógica de negocio (Python o Node) | `AGENTS.md`, `agents.yaml` | Trabaja en ramas; acuerda el contrato de API antes de implementar |
| 02-construccion | `desarrollador-frontend` | Implementa pantallas, componentes y servicios que consumen la API | `AGENTS.md`, `agents.yaml` | Trabaja en ramas; no consume endpoints sin contrato acordado |
| 02-construccion | `infraestructura` | Propone cambios de IaC y explica el impacto de cada `diff`/`plan` | `infra/`, `agents.yaml` | CDK en Python o Terraform; solo plan/diff, nunca apply |
| 02-construccion | `cicd` | Mantiene los pipelines de GitHub Actions y diagnostica sus fallos | `agents.yaml` | Mantiene workflows; producción solo con aprobación manual |
| 02-construccion | `github` | Revisa el estado de uno o varios repos y prepara ramas, commits y PRs | `AGENTS.md`, `agents.yaml` | No edita archivos; commit y push solo con orden explícita |
| 03-validacion | `qa` | Escribe y ejecuta pruebas, verifica criterios de aceptación y reporta la cobertura | `AGENTS.md` | Usa el framework del proyecto; solo toca archivos de prueba |
| 03-validacion | `revisor` | Revisa PRs: corrección, claridad, convenciones y ADRs | `AGENTS.md`, `docs/adr/` | Comenta PRs; nunca aprueba ni hace merge |
| 03-validacion | `seguridad` | Detecta vulnerabilidades, secretos expuestos y permisos IAM excesivos | `docs/seguridad.md` | bandit, pip-audit, detección de secretos, revisión de IAM |
| 04-operacion | `observabilidad` | Diagnostica errores en producción a partir de logs y alarmas | `docs/runbooks/` | Analiza logs y alarmas de CloudWatch; abre issues con diagnóstico |
| 04-operacion | `costos` | Controla el gasto de AWS frente al presupuesto y estima el costo de cada cambio | `agents.yaml` (presupuesto) | Revisa costos y estima el impacto de cambios de infra |
| 04-operacion | `documentacion` | Mantiene la documentación al día después de cada merge | `docs/`, `README` | Actualiza docs y changelog tras cada merge |

### Proyectos con varios repositorios

Si un proyecto vive en varios repos agrupados en una carpeta (workspace) que no es un repo git, pon en su `CLAUDE.md` o `AGENTS.md` una tabla de repos (carpeta local, remoto y qué contiene). Los agentes la leen primero, luego el `AGENTS.md`/`CLAUDE.md` de cada repo, y operan cada repo con `git -C`. Cada repo lleva su propio `agents.yaml`, y un cambio que cruza repos son PRs separados.

Para trabajar un requerimiento que cruza repos, abre la sesión con el líder: `claude --agent agent-platform:tech-lead`.

## Instalar el plugin en un proyecto

Desde Claude Code, en el proyecto:

```text
/plugin marketplace add DanielYes/agent-platform
/plugin install agent-platform@agent-platform
```

Para fijar una versión: `/plugin marketplace add DanielYes/agent-platform@v0.1.0`.

Luego invoca un agente por su nombre (por ejemplo, "usa el agente agent-platform:revisor para revisar mi rama") o abre una sesión con él como agente principal: `claude --agent agent-platform:onboarding`.

## Llamar los workflows

Todos son `on: workflow_call`. Fija siempre una versión (`@v0.1.0`).

### CI, seguridad y despliegue

```yaml
# .github/workflows/ci.yml del proyecto
name: ci
on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci:
    uses: DanielYes/agent-platform/.github/workflows/ci-python.yml@v0.1.0
    with:
      python-version: "3.12"
      coverage-min: 80

  seguridad:
    uses: DanielYes/agent-platform/.github/workflows/security-scan.yml@v0.1.0

  deploy:
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    needs: [ci, seguridad]
    uses: DanielYes/agent-platform/.github/workflows/deploy-aws.yml@v0.1.0
    permissions:
      id-token: write
      contents: read
    with:
      aws-region: us-east-1
      role-arn-staging: ${{ vars.AWS_ROLE_ARN_STAGING }}
      role-arn-prod: ${{ vars.AWS_ROLE_ARN_PROD }}
```

| Workflow | Inputs | Notas |
|---|---|---|
| `ci-python.yml` | `python-version` (`3.12`), `coverage-min` (`80`) | ruff, pytest con cobertura y `python -m build` si hay `pyproject.toml`. |
| `security-scan.yml` | `python-version`, `source-path` | bandit, pip-audit y trufflehog (secretos verificados y desconocidos). |
| `deploy-aws.yml` | `aws-region`, `role-arn-staging`, `role-arn-prod`; opcionales `deploy-command`, `working-directory` (`infra`), `python-version` | OIDC sin access keys. Staging → aprobación del environment `production` → producción. |

Para la aprobación manual, en el repositorio del proyecto crea los environments `staging` y `production` y agrega **Required reviewers** a `production`.

### Workflows de agentes

Usan la [GitHub Action de Claude Code](https://github.com/anthropics/claude-code-action) (`anthropics/claude-code-action@v1`), que instala este plugin desde el marketplace (fijado a `platform-ref`, por defecto `v0.1.0`) y ejecuta cada agente con `--agent agent-platform:<nombre>` y una lista cerrada de herramientas. Solo corren los agentes con `enabled: true` en el `agents.yaml` del proyecto.

La API key llega como secret del repositorio que llama; nunca se escribe en un archivo. Crea el secret `ANTHROPIC_API_KEY` en el proyecto (o en la organización) e instala la GitHub App de Claude en el repositorio (`/install-github-app` desde Claude Code).

| Workflow | Disparador en el proyecto | Agentes | Permisos que debe conceder el caller |
|---|---|---|---|
| `on-issue-opened.yml` | `issues: [opened]` | `producto` → `tech-lead` | `contents: read`, `issues: write`, `id-token: write` |
| `on-pr-opened.yml` | `pull_request: [opened, synchronize, ready_for_review, reopened]` | `revisor`, `qa`, `seguridad`, `arquitecto` (solo PRs grandes) | `contents: read`, `pull-requests: write`, `issues: read`, `id-token: write` |
| `on-pr-infra.yml` | `pull_request` con `paths: ["infra/**"]` | `infraestructura`, `costos` | `contents: read`, `pull-requests: write`, `id-token: write` |
| `on-merge-main.yml` | `push` a la rama de integración (`git.rama_integracion`) | `documentacion` | `contents: write`, `pull-requests: write`, `id-token: write` |
| `scheduled-weekly.yml` | `schedule` + `workflow_dispatch` | `tech-lead`, `observabilidad`, `costos`, `seguridad` | `contents: read`, `issues: write`, `id-token: write` |

Ejemplo:

```yaml
# .github/workflows/agentes-pr.yml del proyecto
name: agentes-pr
on:
  pull_request:
    types: [opened, synchronize, ready_for_review, reopened]

jobs:
  agentes:
    uses: DanielYes/agent-platform/.github/workflows/on-pr-opened.yml@v0.1.0
    permissions:
      contents: read
      pull-requests: write
      issues: read
      id-token: write
    secrets:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Cada workflow trae en su cabecera un ejemplo de uso completo. Los ARNs de los roles de AWS se pasan como inputs desde variables del proyecto (`vars.*`).

## Adoptar la plataforma en un proyecto nuevo

1. **Plantillas.** Copia `templates/agents.yaml.template` a `agents.yaml` y `templates/AGENTS.md.template` a `AGENTS.md` en la raíz del proyecto (o deja que el paso 3 los genere).
2. **IaC de OIDC.** Despliega `iac/` en cada cuenta de AWS del proyecto con sus repositorios como parámetros (ver [`iac/README.md`](iac/README.md)) y guarda los ARNs de salida como variables del repositorio.
3. **Onboarding.** Instala el plugin y ejecuta `claude --agent agent-platform:onboarding`. El agente escanea el repositorio y abre un PR con borradores de `AGENTS.md`, `agents.yaml` y `docs/`.
4. **Revisión humana.** Revisa el PR, resuelve cada `TODO(humano):` (incluido el modelo de ramas del bloque `git`), corrige lo que el agente dedujo mal y haz merge.
5. **Activar agentes.** Agrega los workflows que necesites en `.github/workflows/` del proyecto, crea el secret `ANTHROPIC_API_KEY` y cambia a `enabled: true` en `agents.yaml` los agentes que quieras activar, empezando por los de solo lectura.

## Qué nunca va en este repo

Este repositorio es **público**. Nunca agregues:

- Secretos, tokens, API keys, contraseñas ni archivos `.env`.
- Números de cuenta de AWS, ARNs reales ni IDs de recursos. Usa placeholders como `<ACCOUNT_ID>`.
- Nombres de organizaciones o personas para las que se desarrolla un proyecto, ni datos de sus usuarios.
- URLs, hosts o endpoints internos.
- Contexto de un proyecto concreto: `AGENTS.md`, `agents.yaml`, `docs/` y runbooks viven en el repositorio del proyecto.

Si algo de esto llega a un commit, **rótalo** aunque lo borres después: el historial de un repositorio público ya fue expuesto.

## Versionado

[SemVer](https://semver.org/lang/es/). Cada versión es un tag `vX.Y.Z`; los proyectos fijan el tag en `uses:` y en `platform-ref`. Los cambios se registran en [`CHANGELOG.md`](CHANGELOG.md).

## Licencia

[MIT](LICENSE).
