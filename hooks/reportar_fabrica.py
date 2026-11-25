#!/usr/bin/env python3
"""Hook de agent-platform: avisa a la fábrica cuándo un agente empieza y termina.

No hace nada si FABRICA_URL no está definida. Nunca bloquea ni imprime en stdout:
cualquier error se ignora para no afectar la sesión de Claude Code.

Variables (p. ej. en "env" de ~/.claude/settings.json):
  FABRICA_URL      http://<servidor>:8787
  FABRICA_TOKEN    el mismo token del servidor
  FABRICA_MAQUINA  nombre visible de esta máquina (default: hostname)
  FABRICA_USUARIO  nombre visible de la persona (default: usuario del sistema)
"""

import getpass
import json
import os
import re
import socket
import subprocess
import sys
import urllib.request


def proyecto(cwd):
    try:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=2).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
        if m:
            return m.group(1)
    except Exception:
        pass
    return os.path.basename(os.path.normpath(cwd or "")) or "?"


def main():
    url = os.environ.get("FABRICA_URL", "").rstrip("/")
    if not url:
        return
    entrada = json.load(sys.stdin)
    hook = entrada.get("hook_event_name")
    sesion = entrada.get("session_id", "")
    evento = {
        "sesion": sesion,
        "proyecto": proyecto(entrada.get("cwd", "")),
        "maquina": os.environ.get("FABRICA_MAQUINA") or socket.gethostname(),
        "usuario": os.environ.get("FABRICA_USUARIO") or getpass.getuser(),
    }
    if hook == "PreToolUse":
        datos = entrada.get("tool_input") or {}
        # Solo la descripción corta (3-5 palabras); el encargo completo no sale de la máquina.
        evento.update(estado="tarea", agente=datos.get("subagent_type") or "general-purpose",
                      tarea=(datos.get("description") or "")[:120])
    elif hook in ("SubagentStart", "SubagentStop"):
        evento.update(estado="inicio" if hook == "SubagentStart" else "fin",
                      id=f"{sesion}:{entrada.get('agent_id', '')}",
                      agente=entrada.get("agent_type") or "general-purpose")
    else:
        return
    peticion = urllib.request.Request(
        f"{url}/eventos", data=json.dumps(evento).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ.get('FABRICA_TOKEN', '')}"})
    urllib.request.urlopen(peticion, timeout=2).close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
