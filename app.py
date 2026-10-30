# -*- coding: utf-8 -*-
import os
import re
from flask import Flask, jsonify, render_template, request
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Conexión Neon PostgreSQL
DB_URI = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_uBxvgk0iyXK8@ep-fragrant-fog-b5cyavrb-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&connect_timeout=5",
)


def get_db():
    return psycopg2.connect(DB_URI, cursor_factory=RealDictCursor, connect_timeout=5)


def obtener_periodo_activo():
    """Lee el periodo actual desde la Variable de Entorno en Render."""
    return os.environ.get("PERIODO_ACTUAL", "2026_04")


@app.route("/")
def index():
    periodo_activo = obtener_periodo_activo()
    return render_template("index.html", periodo=periodo_activo)


@app.route("/api/consulta_alumno")
def api_consulta_alumno():
    q = request.args.get("q", "").strip()
    id_periodo = obtener_periodo_activo()

    if not q or len(q) < 3:
        return jsonify(
            {
                "resultados": [],
                "mensaje": "Ingresa al menos 3 caracteres de tu boleta.",
            }
        )

    try:
        conn = get_db()
        cur = conn.cursor()

        # Consulta directa sobre inscripciones filtrando estrictamente por id_periodo
        sql = """
            SELECT DISTINCT
                TRIM(CAST(i.matricula AS VARCHAR)) AS boleta,
                COALESCE(i.grupo, 'S/G')::text AS grupo,
                COALESCE(g.turno, 'S/T')::text AS turno,
                COALESCE(g.salon, 'S/S')::text AS salon
            FROM inscripciones i
            LEFT JOIN grupos g 
                ON TRIM(CAST(i.id_grupo AS VARCHAR)) = TRIM(CAST(g.id_grupo AS VARCHAR))
            WHERE TRIM(CAST(i.id_periodo AS VARCHAR)) = %s
              AND TRANSLATE(LOWER(TRIM(CAST(i.matricula AS VARCHAR))), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') 
                  LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
            ORDER BY boleta ASC
            LIMIT 5;
        """

        patron = f"%{q}%"
        cur.execute(sql, (id_periodo, patron))
        r = cur.fetchall()
        conn.close()

        return jsonify({"resultados": r})
    except Exception as e:
        print(f"Error en consulta de alumnos: {e}")
        return jsonify(
            {
                "resultados": [],
                "error": "Ocurrió un error al procesar la consulta.",
            }
        ), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8085))
    app.run(host="0.0.0.0", port=port, debug=True)