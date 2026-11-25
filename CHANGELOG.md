# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Added

- Bloque `git` en `agents.yaml` (`rama_integracion`, `rama_produccion`). Los agentes que crean ramas eligen la base y el destino del PR según la solicitud y preguntan cuando no está claro.
- Agentes `desarrollador-frontend` y `github` (estado de repos, ramas, commits y PRs con orden explícita).
- `tech-lead` funciona también como líder de sesión (`claude --agent agent-platform:tech-lead`): planea, delega, exige el contrato de API y consolida.
- `producto` redacta historias de usuario y genera el entregable con la plantilla del proyecto (p. ej. PDF).
- Soporte para workspaces con varios repositorios.
- `onboarding` detecta el modelo de ramas del repositorio y `revisor` señala PRs con una rama destino incorrecta.

### Changed

- **Incompatible:** `desarrollador-python` pasa a llamarse `desarrollador-backend` y admite Python o Node. Actualiza `agents.yaml` y cualquier invocación por nombre.
- `qa` usa el framework de pruebas del proyecto en vez de asumir pytest, y no introduce uno nuevo sin aprobación.
- Los agentes aceptan `CLAUDE.md` como alternativa a `AGENTS.md`.
- `tech-lead` usa el modelo `opus`.
- `on-merge-main` abre el PR de documentación hacia la rama que recibió el merge, no siempre hacia `main`.
- README: columna "Para qué sirve" en la tabla de agentes.

## [0.1.0] - 2026-11-24

### Added

- Manifiestos de plugin y marketplace de Claude Code (`.claude-plugin/`).
- 13 subagentes agrupados por fase: `tech-lead`, `onboarding`, `producto`, `arquitecto`, `desarrollador-python`, `infraestructura`, `cicd`, `qa`, `revisor`, `seguridad`, `observabilidad`, `costos` y `documentacion`.
- Workflows reutilizables: `ci-python`, `security-scan` y `deploy-aws`.
- Workflows de agentes: `on-issue-opened`, `on-pr-opened`, `on-pr-infra`, `on-merge-main` y `scheduled-weekly`.
- Stack de CDK en Python con el proveedor OIDC de GitHub y los roles `infra-readonly`, `cicd-deployer`, `observabilidad-logs`, `costos-billing` y `seguridad-audit`.
- Plantillas `AGENTS.md.template` y `agents.yaml.template`.

[Unreleased]: https://github.com/DanielYes/agent-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DanielYes/agent-platform/releases/tag/v0.1.0
