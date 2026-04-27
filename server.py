from __future__ import annotations

import json
import mimetypes
import sqlite3
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "boletins.sqlite"
HOST = "127.0.0.1"
DEFAULT_PORT = 8080


COLUMNS = {
    "id": "id",
    "codigo": "codigo",
    "dataOcorrencia": "data_ocorrencia",
    "horaOcorrencia": "hora_ocorrencia",
    "turno": "turno",
    "status": "status",
    "unidade": "unidade",
    "setor": "setor",
    "local": "localizacao",
    "tipo": "tipo",
    "gravidade": "gravidade",
    "parada": "parada",
    "registradoPor": "registrado_por",
    "envolvidos": "envolvidos",
    "responsavel": "responsavel",
    "prazo": "prazo",
    "descricao": "descricao",
    "acaoImediata": "acao_imediata",
    "causaProvavel": "causa_provavel",
    "acaoCorretiva": "acao_corretiva",
    "observacoes": "observacoes",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ocorrencias (
                id TEXT PRIMARY KEY,
                codigo TEXT NOT NULL UNIQUE,
                data_ocorrencia TEXT NOT NULL,
                hora_ocorrencia TEXT NOT NULL,
                turno TEXT NOT NULL,
                status TEXT NOT NULL,
                unidade TEXT,
                setor TEXT NOT NULL,
                localizacao TEXT,
                tipo TEXT NOT NULL,
                gravidade TEXT NOT NULL,
                parada INTEGER DEFAULT 0,
                registrado_por TEXT NOT NULL,
                envolvidos TEXT,
                responsavel TEXT,
                prazo TEXT,
                descricao TEXT NOT NULL,
                acao_imediata TEXT,
                causa_provavel TEXT,
                acao_corretiva TEXT,
                observacoes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_status ON ocorrencias(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_data ON ocorrencias(data_ocorrencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_gravidade ON ocorrencias(gravidade)")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def make_code(conn: sqlite3.Connection, date_value: str | None) -> str:
    year = (date_value or datetime.now().strftime("%Y"))[:4]
    rows = conn.execute(
        "SELECT codigo FROM ocorrencias WHERE codigo LIKE ?",
        (f"BO-{year}-%",),
    ).fetchall()
    numbers: list[int] = []
    for row in rows:
        try:
            numbers.append(int(str(row["codigo"]).split("-")[-1]))
        except ValueError:
            continue
    return f"BO-{year}-{max(numbers, default=0) + 1:04d}"


def row_to_record(row: sqlite3.Row) -> dict:
    return {api_key: row[column] for api_key, column in COLUMNS.items()}


def clean_record(record: dict, conn: sqlite3.Connection, existing: sqlite3.Row | None = None) -> dict:
    timestamp = now_iso()
    cleaned = {key: record.get(key, "") for key in COLUMNS}
    cleaned["id"] = cleaned.get("id") or str(uuid4())
    cleaned["dataOcorrencia"] = cleaned.get("dataOcorrencia") or datetime.now().strftime("%Y-%m-%d")
    cleaned["horaOcorrencia"] = cleaned.get("horaOcorrencia") or "00:00"
    cleaned["status"] = cleaned.get("status") or "Aberto"
    cleaned["parada"] = int(cleaned.get("parada") or 0)
    cleaned["codigo"] = cleaned.get("codigo") or make_code(conn, cleaned["dataOcorrencia"])
    cleaned["createdAt"] = cleaned.get("createdAt") or (existing["created_at"] if existing else timestamp)
    cleaned["updatedAt"] = timestamp
    return cleaned


def required_missing(record: dict) -> list[str]:
    labels = {
        "dataOcorrencia": "data",
        "horaOcorrencia": "hora",
        "turno": "turno",
        "setor": "setor",
        "tipo": "tipo",
        "gravidade": "gravidade",
        "registradoPor": "registrado por",
        "descricao": "descrição",
    }
    return [label for key, label in labels.items() if not str(record.get(key) or "").strip()]


def save_record(record: dict) -> dict:
    with connect() as conn:
        existing = None
        if record.get("id"):
            existing = conn.execute("SELECT * FROM ocorrencias WHERE id = ?", (record["id"],)).fetchone()
        cleaned = clean_record(record, conn, existing)
        missing = required_missing(cleaned)
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(missing)}")

        keys = list(COLUMNS)
        db_columns = [COLUMNS[key] for key in keys]
        values = [cleaned[key] for key in keys]
        placeholders = ", ".join("?" for _ in keys)
        updates = ", ".join(f"{column}=excluded.{column}" for column in db_columns if column != "id")
        conn.execute(
            f"""
            INSERT INTO ocorrencias ({", ".join(db_columns)})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {updates}
            """,
            values,
        )
        row = conn.execute("SELECT * FROM ocorrencias WHERE id = ?", (cleaned["id"],)).fetchone()
        return row_to_record(row)


def list_records() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ocorrencias
            ORDER BY data_ocorrencia DESC, hora_ocorrencia DESC, codigo DESC
            """
        ).fetchall()
        return [row_to_record(row) for row in rows]


def get_record(record_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM ocorrencias WHERE id = ?", (record_id,)).fetchone()
        return row_to_record(row) if row else None


def delete_record(record_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM ocorrencias WHERE id = ?", (record_id,))
        return cursor.rowcount > 0


def replace_records(records: list[dict]) -> list[dict]:
    with connect() as conn:
        conn.execute("DELETE FROM ocorrencias")
    saved: list[dict] = []
    for record in records:
        if isinstance(record, dict):
            saved.append(save_record(record))
    return saved


class AppHandler(BaseHTTPRequestHandler):
    server_version = "BoletimOcorrencias/1.0"

    def log_message(self, format: str, *args) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self.send_json({"ok": True, "database": str(DB_PATH)})
            return
        if path == "/api/records":
            self.send_json(list_records())
            return
        if path.startswith("/api/records/"):
            record = get_record(unquote(path.rsplit("/", 1)[-1]))
            if not record:
                self.send_json({"error": "Registro não encontrado"}, 404)
                return
            self.send_json(record)
            return
        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/records":
            self.send_json({"error": "Rota não encontrada"}, 404)
            return
        try:
            record = self.read_json()
            if not isinstance(record, dict):
                raise ValueError("JSON inválido")
            self.send_json(save_record(record), 201)
        except (json.JSONDecodeError, ValueError, sqlite3.IntegrityError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/records":
            self.send_json({"error": "Rota não encontrada"}, 404)
            return
        try:
            records = self.read_json()
            if not isinstance(records, list):
                raise ValueError("A importação deve ser uma lista de registros")
            self.send_json(replace_records(records))
        except (json.JSONDecodeError, ValueError, sqlite3.IntegrityError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/records/"):
            self.send_json({"error": "Rota não encontrada"}, 404)
            return
        record_id = unquote(parsed.path.rsplit("/", 1)[-1])
        existing = get_record(record_id)
        if not existing:
            self.send_json({"error": "Registro não encontrado"}, 404)
            return
        try:
            updates = self.read_json()
            if not isinstance(updates, dict):
                raise ValueError("JSON inválido")
            existing.update(updates)
            self.send_json(save_record(existing))
        except (json.JSONDecodeError, ValueError, sqlite3.IntegrityError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/records/"):
            self.send_json({"error": "Rota não encontrada"}, 404)
            return
        deleted = delete_record(unquote(parsed.path.rsplit("/", 1)[-1]))
        self.send_json({"deleted": deleted}, 200 if deleted else 404)

    def serve_static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
        target = (ROOT / requested).resolve()
        if DATA_DIR in target.parents or target == DATA_DIR:
            self.send_error(403)
            return
        if not str(target).startswith(str(ROOT)) or not target.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer((HOST, port), AppHandler)
    print(f"Sistema iniciado em http://{HOST}:{port}")
    print(f"Banco SQLite: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
