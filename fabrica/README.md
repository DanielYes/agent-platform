# Fábrica de agentes

**Alcance:** cómo instalar y operar la vista en vivo de los agentes de `agent-platform`
en una red local: el servidor, la página 3D y la configuración de cada máquina.

**Fuera de alcance:** la definición de los agentes (`agents/`) y los workflows de CI.

## Cómo funciona

```
 Equipo A (hook) ──┐
                   ├──► servidor.py (equipo siempre encendido) ──► SQLite
 Equipo B (hook) ──┘       │  POST /eventos   (con token)
                           │  GET  /estado    (la página consulta cada 4 s)
                           │  GET  /          (página 3D)
                           └─ cada 2 min: `gh` → issues, PRs y runs de los repos con el topic
                                                     ▲
 Navegador en la red ─────────────────────────────────┘  http://<servidor>:8787
```

- **Hook** (`../hooks/`): viene con el plugin. Reporta cuándo un agente empieza
  (`SubagentStart`) y termina (`SubagentStop`), y la descripción corta de la tarea
  (`PreToolUse` de `Agent`, 3-5 palabras). **El encargo completo nunca sale de la
  máquina.** Si `FABRICA_URL` no está definida, no hace nada.
- **Servidor** (`servidor.py`): solo librería estándar de Python 3.10+, sin
  dependencias. Guarda las tareas en SQLite y borra el historial de más de 24 h.
- **Página** (`index.html`): three.js desde jsDelivr (el navegador necesita internet).
  Cada agente es una estación; cada tarea activa, un trabajador del color de su
  máquina. Los PRs abiertos van en la cinta y los issues en pilas por repo.

Una tarea sin evento de fin durante 30 minutos (sesión cerrada, equipo apagado) pasa a
`perdida` y sale de la planta.

## 1. Instalar el servidor

En el equipo que queda siempre encendido, con Python 3.10+ y `gh` autenticado
(`gh auth status`). `gh` es lo que permite ver repos privados: el servidor ve lo mismo
que esa cuenta.

```bash
git clone https://github.com/DanielYes/agent-platform.git
cd agent-platform/fabrica
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # guarda este token
FABRICA_TOKEN=<token> python3 servidor.py
```

Abre `http://<ip-del-servidor>:8787` desde otro equipo. Si no carga, abre el puerto
8787 en el firewall de ese equipo **solo para la red local**.

### Dejarlo corriendo

- **Linux (systemd):** crea `/etc/systemd/system/fabrica.service`:

  ```ini
  [Unit]
  Description=Fábrica de agentes
  After=network-online.target

  [Service]
  User=<usuario-con-gh-autenticado>
  WorkingDirectory=/ruta/agent-platform/fabrica
  Environment=FABRICA_TOKEN=<token>
  ExecStart=/usr/bin/python3 servidor.py
  Restart=on-failure

  [Install]
  WantedBy=multi-user.target
  ```

  Luego: `sudo systemctl enable --now fabrica`.
- **Windows:** crea una tarea en el Programador de tareas que se ejecute "al iniciar el
  sistema", con el usuario que tiene `gh` autenticado, que ejecute
  `python servidor.py` en la carpeta `fabrica` y con la variable `FABRICA_TOKEN`
  definida en las variables de entorno de ese usuario.

### Variables del servidor

| Variable | Default | Uso |
|---|---|---|
| `FABRICA_TOKEN` | (obligatoria) | Token que deben enviar los hooks. |
| `FABRICA_PUERTO` | `8787` | Puerto HTTP. |
| `FABRICA_HOST` | `0.0.0.0` | Interfaz donde escucha (toda la red local). |
| `FABRICA_DB` | `fabrica.db` | Ruta del SQLite. |
| `FABRICA_TOPIC` | `agent-factory` | Topic de los repos que se muestran. |
| `FABRICA_DUENOS` | tu usuario y tus orgs | Dónde buscar el topic. Sin esto aparecerían repos de terceros con el mismo topic. |
| `FABRICA_GITHUB_SEGUNDOS` | `120` | Frecuencia de consulta a GitHub; `0` la desactiva. |
| `FABRICA_MINUTOS_PERDIDA` | `30` | Minutos sin evento de fin para marcar una tarea como perdida. |
| `FABRICA_OCULTAR` | (vacío) | Proyectos a ocultar, separados por coma (`org/repo,Carpeta`). |

## 2. Configurar cada máquina que reporta

1. Instala o actualiza el plugin (`/plugin marketplace update agent-platform`): el hook
   viene incluido.
2. Agrega a `~/.claude/settings.json` de esa máquina:

   ```json
   {
     "env": {
       "FABRICA_URL": "http://<ip-del-servidor>:8787",
       "FABRICA_TOKEN": "<token>",
       "FABRICA_MAQUINA": "portatil-daniel"
     }
   }
   ```

   `FABRICA_MAQUINA` y `FABRICA_USUARIO` son opcionales (por defecto, el hostname y el
   usuario del sistema).
3. Abre una sesión nueva de Claude Code y pide algo que use un agente. Debe aparecer un
   trabajador en su estación.

Requisitos del hook: `python3` y `bash` en el `PATH`. En WSL, Linux y macOS ya están.
En Windows nativo hace falta Git Bash y Python; sin ellos el hook no reporta, pero
tampoco afecta la sesión.

## 3. Elegir qué proyectos se ven

- **Issues, PRs y runs:** solo de los repos con el topic `agent-factory`:
  `gh repo edit <org>/<repo> --add-topic agent-factory`.
- **Agentes trabajando:** se ven todos los proyectos de las máquinas configuradas.
  Para ocultar alguno, ponlo en `FABRICA_OCULTAR` del servidor. El nombre es
  `org/repo` si la sesión corre dentro de un repo, o el nombre de la carpeta si no
  (p. ej. un workspace con varios repos).
- La página tiene además filtros por proyecto y máquina, que solo ocultan en tu vista.

## Seguridad

- La página y `/estado` no piden autenticación: cualquiera en la red local los ve.
  No expongas el puerto a internet.
- Los hooks envían agente, descripción corta, proyecto, máquina y usuario. Nada de
  código, prompts completos ni secretos.
- El token solo protege la escritura de eventos.
