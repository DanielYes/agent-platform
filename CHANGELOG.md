# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [SemVer](https://semver.org/lang/es/).

## [Unreleased]

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
