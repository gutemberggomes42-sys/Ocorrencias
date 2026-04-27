from __future__ import annotations

import cgi
import json
import mimetypes
import os
import sqlite3
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "boletins.sqlite"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USING_POSTGRES = bool(DATABASE_URL)
HOST = os.getenv("HOST") or ("0.0.0.0" if os.getenv("RENDER") else "127.0.0.1")
DEFAULT_PORT = int(os.getenv("PORT", "8080"))
MAX_PHOTO_SIZE = int(os.getenv("MAX_PHOTO_MB", "8")) * 1024 * 1024
MAX_PHOTOS_PER_UPLOAD = int(os.getenv("MAX_PHOTOS_PER_UPLOAD", "8"))
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Local SQLite mode does not need psycopg installed.
    psycopg = None
    dict_row = None


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


PHOTO_COLUMNS = {
    "id": "id",
    "recordId": "record_id",
    "filename": "filename",
    "contentType": "content_type",
    "size": "size",
    "createdAt": "created_at",
}


class Database:
    placeholder = "?"

    def __init__(self) -> None:
        self.using_postgres = USING_POSTGRES
        if self.using_postgres:
            if psycopg is None:
                raise RuntimeError("psycopg não instalado. Rode: pip install -r requirements.txt")
            self.placeholder = "%s"

    def connect(self):
        if self.using_postgres:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)

        DATA_DIR.mkdir(exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def ddl(self) -> tuple[str, str]:
        if self.using_postgres:
            return (
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
                """,
                """
                CREATE TABLE IF NOT EXISTS fotos (
                    id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL REFERENCES ocorrencias(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    data BYTEA NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )

        return (
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
            """,
            """
            CREATE TABLE IF NOT EXISTS fotos (
                id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                data BLOB NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(record_id) REFERENCES ocorrencias(id) ON DELETE CASCADE
            )
            """,
        )


db = Database()


def init_db() -> None:
    ocorrencias_ddl, fotos_ddl = db.ddl()
    with db.connect() as conn:
        conn.execute(ocorrencias_ddl)
        conn.execute(fotos_ddl)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_status ON ocorrencias(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_data ON ocorrencias(data_ocorrencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ocorrencias_gravidade ON ocorrencias(gravidade)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fotos_record_id ON fotos(record_id)")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def row_value(row, column: str):
    return row[column]


def make_code(conn, date_value: str | None) -> str:
    year = (date_value or datetime.now().strftime("%Y"))[:4]
    rows = conn.execute(
        f"SELECT codigo FROM ocorrencias WHERE codigo LIKE {db.placeholder}",
        (f"BO-{year}-%",),
    ).fetchall()
    numbers: list[int] = []
    for row in rows:
        try:
            numbers.append(int(str(row_value(row, "codigo")).split("-")[-1]))
        except ValueError:
            continue
    return f"BO-{year}-{max(numbers, default=0) + 1:04d}"


def photo_meta(row) -> dict:
    meta = {api_key: row_value(row, column) for api_key, column in PHOTO_COLUMNS.items()}
    meta["url"] = f"/api/photos/{meta['id']}"
    return meta


def list_photos(record_id: str, conn=None) -> list[dict]:
    close_conn = conn is None
    conn = conn or db.connect()
    try:
        rows = conn.execute(
            f"""
            SELECT id, record_id, filename, content_type, size, created_at
            FROM fotos
            WHERE record_id = {db.placeholder}
            ORDER BY created_at ASC
            """,
            (record_id,),
        ).fetchall()
        return [photo_meta(row) for row in rows]
    finally:
        if close_conn:
            conn.close()


def row_to_record(row, conn=None) -> dict:
    record = {api_key: row_value(row, column) for api_key, column in COLUMNS.items()}
    photos = list_photos(record["id"], conn)
    record["photos"] = photos
    record["photoCount"] = len(photos)
    return record


def clean_record(record: dict, conn, existing=None) -> dict:
    timestamp = now_iso()
    cleaned = {key: record.get(key, "") for key in COLUMNS}
    cleaned["id"] = cleaned.get("id") or str(uuid4())
    cleaned["dataOcorrencia"] = cleaned.get("dataOcorrencia") or datetime.now().strftime("%Y-%m-%d")
    cleaned["horaOcorrencia"] = cleaned.get("horaOcorrencia") or "00:00"
    cleaned["status"] = cleaned.get("status") or "Aberto"
    cleaned["parada"] = int(cleaned.get("parada") or 0)
    cleaned["codigo"] = cleaned.get("codigo") or make_code(conn, cleaned["dataOcorrencia"])
    cleaned["createdAt"] = cleaned.get("createdAt") or (row_value(existing, "created_at") if existing else timestamp)
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
    with db.connect() as conn:
        existing = None
        if record.get("id"):
            existing = conn.execute(
                f"SELECT * FROM ocorrencias WHERE id = {db.placeholder}",
                (record["id"],),
            ).fetchone()
        cleaned = clean_record(record, conn, existing)
        missing = required_missing(cleaned)
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(missing)}")

        keys = list(COLUMNS)
        db_columns = [COLUMNS[key] for key in keys]
        values = [cleaned[key] for key in keys]
        placeholders = ", ".join(db.placeholder for _ in keys)
        updates = ", ".join(f"{column}=excluded.{column}" for column in db_columns if column != "id")
        conn.execute(
            f"""
            INSERT INTO ocorrencias ({", ".join(db_columns)})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {updates}
            """,
            values,
        )
        row = conn.execute(
            f"SELECT * FROM ocorrencias WHERE id = {db.placeholder}",
            (cleaned["id"],),
        ).fetchone()
        return row_to_record(row, conn)


def list_records() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM ocorrencias
            ORDER BY data_ocorrencia DESC, hora_ocorrencia DESC, codigo DESC
            """
        ).fetchall()
        return [row_to_record(row, conn) for row in rows]


def get_record(record_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT * FROM ocorrencias WHERE id = {db.placeholder}",
            (record_id,),
        ).fetchone()
        return row_to_record(row, conn) if row else None


def delete_record(record_id: str) -> bool:
    with db.connect() as conn:
        cursor = conn.execute(
            f"DELETE FROM ocorrencias WHERE id = {db.placeholder}",
            (record_id,),
        )
        return cursor.rowcount > 0


def replace_records(records: list[dict]) -> list[dict]:
    with db.connect() as conn:
        conn.execute("DELETE FROM ocorrencias")
    saved: list[dict] = []
    for record in records:
        if isinstance(record, dict):
            saved.append(save_record(record))
    return saved


def save_photos(record_id: str, files: list[tuple[str, str, bytes]]) -> list[dict]:
    if not get_record(record_id):
        raise ValueError("Registro não encontrado")

    saved: list[dict] = []
    with db.connect() as conn:
        for filename, content_type, data in files:
            photo_id = str(uuid4())
            conn.execute(
                f"""
                INSERT INTO fotos (id, record_id, filename, content_type, data, size, created_at)
                VALUES ({", ".join(db.placeholder for _ in range(7))})
                """,
                (photo_id, record_id, filename, content_type, data, len(data), now_iso()),
            )
            row = conn.execute(
                f"""
                SELECT id, record_id, filename, content_type, size, created_at
                FROM fotos
                WHERE id = {db.placeholder}
                """,
                (photo_id,),
            ).fetchone()
            saved.append(photo_meta(row))
    return saved


def get_photo(photo_id: str):
    with db.connect() as conn:
        return conn.execute(
            f"""
            SELECT id, record_id, filename, content_type, data, size, created_at
            FROM fotos
            WHERE id = {db.placeholder}
            """,
            (photo_id,),
        ).fetchone()


def delete_photo(photo_id: str) -> bool:
    with db.connect() as conn:
        cursor = conn.execute(
            f"DELETE FROM fotos WHERE id = {db.placeholder}",
            (photo_id,),
        )
        return cursor.rowcount > 0


class AppHandler(BaseHTTPRequestHandler):
    server_version = "BoletimOcorrencias/2.0"

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

    def parse_photo_upload(self) -> list[tuple[str, str, bytes]]:
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        fields = form["photos"] if "photos" in form else []
        if not isinstance(fields, list):
            fields = [fields]

        files: list[tuple[str, str, bytes]] = []
        for field in fields:
            if not getattr(field, "filename", ""):
                continue
            filename = Path(field.filename).name
            content_type = field.type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            if content_type not in ALLOWED_PHOTO_TYPES:
                raise ValueError(f"Tipo de arquivo não permitido: {content_type}")
            data = field.file.read()
            if len(data) > MAX_PHOTO_SIZE:
                raise ValueError(f"Foto acima do limite de {MAX_PHOTO_SIZE // 1024 // 1024} MB")
            files.append((filename, content_type, data))

        if len(files) > MAX_PHOTOS_PER_UPLOAD:
            raise ValueError(f"Envie no máximo {MAX_PHOTOS_PER_UPLOAD} fotos por vez")
        if not files:
            raise ValueError("Nenhuma foto enviada")
        return files

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "database": "postgresql" if USING_POSTGRES else str(DB_PATH),
                    "photoStorage": "database",
                }
            )
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
        if path.startswith("/api/photos/"):
            row = get_photo(unquote(path.rsplit("/", 1)[-1]))
            if not row:
                self.send_json({"error": "Foto não encontrada"}, 404)
                return
            body = row_value(row, "data")
            if isinstance(body, memoryview):
                body = body.tobytes()
            self.send_response(200)
            self.send_header("Content-Type", row_value(row, "content_type"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f'inline; filename="{row_value(row, "filename")}"')
            self.end_headers()
            self.wfile.write(body)
            return
        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/records":
            try:
                record = self.read_json()
                if not isinstance(record, dict):
                    raise ValueError("JSON inválido")
                self.send_json(save_record(record), 201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return

        if path.startswith("/api/records/") and path.endswith("/photos"):
            record_id = unquote(path.split("/")[-2])
            try:
                files = self.parse_photo_upload()
                self.send_json(save_photos(record_id, files), 201)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return

        self.send_json({"error": "Rota não encontrada"}, 404)

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
        except Exception as exc:
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
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/photos/"):
            deleted = delete_photo(unquote(path.rsplit("/", 1)[-1]))
            self.send_json({"deleted": deleted}, 200 if deleted else 404)
            return
        if path.startswith("/api/records/"):
            deleted = delete_record(unquote(path.rsplit("/", 1)[-1]))
            self.send_json({"deleted": deleted}, 200 if deleted else 404)
            return
        self.send_json({"error": "Rota não encontrada"}, 404)

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
    print(f"Banco: {'PostgreSQL via DATABASE_URL' if USING_POSTGRES else DB_PATH}")
    print("Fotos: armazenadas no banco de dados")
    server.serve_forever()


if __name__ == "__main__":
    main()
