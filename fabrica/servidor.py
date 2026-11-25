#!/usr/bin/env python3
"""Servidor local de la fábrica de agentes.

Recibe eventos de los hooks de Claude Code (POST /eventos), consulta GitHub con `gh`
y sirve la página 3D (GET /) y el estado actual (GET /estado).

Solo usa la librería estándar. Configuración por variables de entorno:

  FABRICA_TOKEN             (obligatorio) token que deben enviar los hooks.
  FABRICA_PUERTO            puerto HTTP (default 8787).
  FABRICA_HOST              interfaz donde escucha (default 0.0.0.0: toda la red local).
  FABRICA_DB                ruta del SQLite (default fabrica.db junto a este archivo).
  FABRICA_TOPIC             topic de GitHub de los repos a mostrar (default agent-factory).
  FABRICA_DUENOS            usuarios u organizaciones donde buscar ese topic, separados por coma
                            (default: tu usuario de `gh` y tus organizaciones).
  FABRICA_GITHUB_SEGUNDOS   cada cuánto consultar GitHub (default 120; 0 lo desactiva).
  FABRICA_MINUTOS_PERDIDA   tarea sin fin tras N minutos = perdida (default 30).
  FABRICA_OCULTAR           proyectos a ocultar, separados por coma (p. ej. org/repo,Otro).
"""

import hmac
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIR = Path(__file__).resolve().parent
TOKEN = os.environ.get("FABRICA_TOKEN", "")
PUERTO = int(os.environ.get("FABRICA_PUERTO", "8787"))
HOST = os.environ.get("FABRICA_HOST", "0.0.0.0")
DB = os.environ.get("FABRICA_DB", str(DIR / "fabrica.db"))
TOPIC = os.environ.get("FABRICA_TOPIC", "agent-factory")
GITHUB_SEGUNDOS = int(os.environ.get("FABRICA_GITHUB_SEGUNDOS", "120"))
MINUTOS_PERDIDA = int(os.environ.get("FABRICA_MINUTOS_PERDIDA", "30"))
DUENOS = [d.strip() for d in os.environ.get("FABRICA_DUENOS", "").split(",") if d.strip()]
OCULTAR = {p.strip() for p in os.environ.get("FABRICA_OCULTAR", "").split(",") if p.strip()}

MAX_CUERPO = 16 * 1024
CAMPOS_TEXTO = {"agente": 80, "tarea": 200, "proyecto": 120, "maquina": 80, "usuario": 80, "sesion": 80}

_db_lock = threading.Lock()
_github = {"habilitado": GITHUB_SEGUNDOS > 0, "actualizado": None, "error": None, "repos": []}


def conectar():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE IF NOT EXISTS tareas (
            id TEXT PRIMARY KEY,
            agente TEXT, tarea TEXT, proyecto TEXT, maquina TEXT, usuario TEXT, sesion TEXT,
            estado TEXT NOT NULL,          -- activa | terminada | perdida
            inicio REAL NOT NULL,
            fin REAL
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS tareas_estado ON tareas(estado, inicio)")
    return con


CON = conectar()


# ---------------------------------------------------------------- eventos

_pendientes = {}  # (sesion, agente) -> descripciones que llegaron antes del inicio


def _clave(sesion, agente):
    return (sesion, agente.rsplit(":", 1)[-1])


def registrar(evento):
    """Aplica un evento a la tabla de tareas.

    estado = inicio | fin  (SubagentStart / SubagentStop, con id = sesion:agent_id)
    estado = tarea         (PreToolUse de Agent: trae la descripción corta, sin id)
    """
    tipo = evento.get("estado")
    datos = {k: str(evento.get(k) or "")[:n] for k, n in CAMPOS_TEXTO.items()}
    if tipo == "tarea":
        return _registrar_descripcion(datos)
    tid = str(evento.get("id", ""))[:200]
    if not tid or tipo not in ("inicio", "fin"):
        raise ValueError("faltan 'id' o 'estado' (inicio|fin|tarea)")
    ahora = time.time()
    with _db_lock:
        if tipo == "inicio":
            if not datos["tarea"]:
                cola = _pendientes.get(_clave(datos["sesion"], datos["agente"]))
                if cola:
                    datos["tarea"] = cola.pop(0)
            CON.execute(
                """INSERT INTO tareas (id, agente, tarea, proyecto, maquina, usuario, sesion, estado, inicio)
                   VALUES (:id, :agente, :tarea, :proyecto, :maquina, :usuario, :sesion, 'activa', :inicio)
                   ON CONFLICT(id) DO UPDATE SET estado='activa', fin=NULL""",
                {**datos, "id": tid, "inicio": ahora},
            )
        else:
            cur = CON.execute(
                "UPDATE tareas SET estado='terminada', fin=? WHERE id=?", (ahora, tid)
            )
            if cur.rowcount == 0:  # llegó el fin sin el inicio (servidor reiniciado)
                CON.execute(
                    """INSERT INTO tareas (id, agente, tarea, proyecto, maquina, usuario, sesion, estado, inicio, fin)
                       VALUES (:id, :agente, :tarea, :proyecto, :maquina, :usuario, :sesion, 'terminada', :t, :t)""",
                    {**datos, "id": tid, "t": ahora},
                )
        CON.commit()


def _registrar_descripcion(datos):
    if not datos["tarea"]:
        return
    with _db_lock:
        # Si el inicio ya llegó, completa la tarea activa más reciente sin descripción.
        fila = CON.execute(
            """SELECT id, agente FROM tareas
               WHERE estado='activa' AND sesion=? AND tarea='' ORDER BY inicio DESC""",
            (datos["sesion"],),
        ).fetchall()
        for f in fila:
            if _clave(datos["sesion"], f["agente"]) == _clave(datos["sesion"], datos["agente"]):
                CON.execute("UPDATE tareas SET tarea=? WHERE id=?", (datos["tarea"], f["id"]))
                CON.commit()
                return
        cola = _pendientes.setdefault(_clave(datos["sesion"], datos["agente"]), [])
        cola.append(datos["tarea"])
        del cola[:-10]
        if len(_pendientes) > 500:  # sesiones viejas que nunca arrancaron su agente
            _pendientes.pop(next(iter(_pendientes)))


def estado_actual():
    ahora = time.time()
    with _db_lock:
        CON.execute(
            "UPDATE tareas SET estado='perdida' WHERE estado='activa' AND inicio < ?",
            (ahora - MINUTOS_PERDIDA * 60,),
        )
        # Historial acotado: lo de las últimas 24 h.
        CON.execute("DELETE FROM tareas WHERE estado!='activa' AND inicio < ?", (ahora - 86400,))
        CON.commit()
        filas = CON.execute(
            """SELECT * FROM tareas
               WHERE estado='activa' OR inicio > ?
               ORDER BY inicio DESC LIMIT 200""",
            (ahora - 3600,),
        ).fetchall()
    tareas = [dict(f) for f in filas if f["proyecto"] not in OCULTAR]
    return {
        "ahora": ahora,
        "activas": [t for t in tareas if t["estado"] == "activa"],
        "recientes": [t for t in tareas if t["estado"] != "activa"][:40],
        "github": _github,
    }


# ---------------------------------------------------------------- GitHub

def gh(*args):
    salida = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if salida.returncode != 0:
        raise RuntimeError(salida.stderr.strip() or f"gh {' '.join(args)} falló")
    return json.loads(salida.stdout or "[]")


def duenos():
    """Sin esto, el topic se buscaría en todo GitHub y aparecerían repos de terceros."""
    if not DUENOS:
        DUENOS.append(gh("api", "user")["login"])
        DUENOS.extend(o["login"] for o in gh("api", "user/orgs"))
    return DUENOS


def consultar_github():
    repos = gh("search", "repos", f"--topic={TOPIC}", f"--owner={','.join(duenos())}",
               "--limit", "50", "--json", "fullName,url,isPrivate")
    resultado = []
    for r in repos:
        nombre = r["fullName"]
        if nombre in OCULTAR:
            continue
        try:
            issues = gh("issue", "list", "-R", nombre, "--limit", "30",
                        "--json", "number,title,url,labels,assignees,updatedAt")
            prs = gh("pr", "list", "-R", nombre, "--limit", "30",
                     "--json", "number,title,url,headRefName,baseRefName,isDraft,author,updatedAt")
            runs = gh("run", "list", "-R", nombre, "--limit", "10",
                      "--json", "databaseId,workflowName,status,conclusion,headBranch,url,createdAt")
        except Exception as e:  # un repo con error no tumba a los demás
            resultado.append({"repo": nombre, "url": r["url"], "error": str(e)[:300]})
            continue
        resultado.append({
            "repo": nombre, "url": r["url"],
            "issues": [{**i, "labels": [l["name"] for l in i.get("labels", [])],
                        "assignees": [a["login"] for a in i.get("assignees", [])]} for i in issues],
            "prs": [{**p, "author": (p.get("author") or {}).get("login")} for p in prs],
            "runs": runs,
        })
    return resultado


def bucle_github():
    while True:
        try:
            _github["repos"] = consultar_github()
            _github["error"] = None
        except Exception as e:
            _github["error"] = str(e)[:300]
        _github["actualizado"] = time.time()
        time.sleep(GITHUB_SEGUNDOS)


# ---------------------------------------------------------------- HTTP

class Manejador(BaseHTTPRequestHandler):
    server_version = "fabrica/1"

    def _responder(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        ruta = self.path.split("?", 1)[0]
        if ruta in ("/", "/index.html"):
            self._responder(200, (DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif ruta == "/estado":
            self._responder(200, estado_actual())
        else:
            self._responder(404, {"error": "no existe"})

    def do_POST(self):
        if self.path != "/eventos":
            return self._responder(404, {"error": "no existe"})
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
            return self._responder(401, {"error": "token inválido"})
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > MAX_CUERPO:
            return self._responder(413, {"error": "cuerpo vacío o demasiado grande"})
        try:
            registrar(json.loads(self.rfile.read(largo)))
        except (ValueError, json.JSONDecodeError) as e:
            return self._responder(400, {"error": str(e)})
        self._responder(204, b"")

    def log_message(self, formato, *args):  # solo errores, sin ruido por cada consulta
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            sys.stderr.write("%s - %s\n" % (self.address_string(), formato % args))


def main():
    if not TOKEN:
        sys.exit("Define FABRICA_TOKEN (p. ej. export FABRICA_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')).")
    if GITHUB_SEGUNDOS > 0:
        threading.Thread(target=bucle_github, daemon=True).start()
    servidor = ThreadingHTTPServer((HOST, PUERTO), Manejador)
    print(f"Fábrica en http://{HOST}:{PUERTO}  (db: {DB}, topic: {TOPIC})", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
