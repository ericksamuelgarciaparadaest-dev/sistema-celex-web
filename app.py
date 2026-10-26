# -*- coding: utf-8 -*-
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Conexión Neon PostgreSQL
DB_URI = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_uBxvgk0iyXK8@ep-fragrant-fog-b5cyavrb-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&connect_timeout=5"
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
        return jsonify({"resultados": [], "mensaje": "Ingresa al menos 3 caracteres de tu boleta."})

    try:
        conn = get_db()
        cur = conn.cursor()
        
        # CTE UNIFICADA: Cruce relacional por matricula, id_periodo e id_grupo
        sql = """
            WITH base_unificada AS (
                SELECT 
                    COALESCE(TRIM(CAST(a.matricula AS VARCHAR)), TRIM(CAST(i.matricula AS VARCHAR))) AS matricula,
                    i.id_periodo,
                    i.id_grupo,
                    i.grupo AS grupo_inscrito,
                    i.id_inscripcion
                FROM alumnos a
                FULL OUTER JOIN inscripciones i 
                    ON TRIM(CAST(a.matricula AS VARCHAR)) = TRIM(CAST(i.matricula AS VARCHAR)) 
                    AND TRIM(CAST(i.id_periodo AS VARCHAR)) = %s
            )
            SELECT DISTINCT
                b.matricula AS boleta,
                COALESCE(b.grupo_inscrito, 'S/G')::text AS grupo,
                COALESCE(g.turno, 'S/T')::text AS turno,
                COALESCE(g.salon, 'S/S')::text AS salon
            FROM base_unificada b
            LEFT JOIN grupos g 
                ON TRIM(CAST(b.id_grupo AS VARCHAR)) = TRIM(CAST(g.id_grupo AS VARCHAR))
            WHERE b.id_inscripcion IS NOT NULL
              AND TRANSLATE(LOWER(b.matricula), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
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
        return jsonify({"resultados": [], "error": "Ocurrió un error al procesar la consulta."}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8085))
    app.run(host='0.0.0.0', port=port, debug=True)