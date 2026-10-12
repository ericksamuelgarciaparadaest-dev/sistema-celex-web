# -*- coding: utf-8 -*-
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = "celex_secret_key_2026"
app.config['TEMPLATES_AUTO_RELOAD'] = True

DB_URI = os.getenv(
    "DATABASE_URL", 
    "postgresql://neondb_owner:npg_uBxvgk0iyXK8@ep-fragrant-fog-b5cyavrb-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&connect_timeout=5"
)

def get_db_connection():
    return psycopg2.connect(DB_URI, cursor_factory=RealDictCursor, connect_timeout=5)

def obtener_tablas_disponibles():
    tablas = []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_type = 'BASE TABLE'
            ORDER BY table_name ASC;
        """)
        tablas = [row['table_name'] for row in cursor.fetchall()]
        cursor.close()
    except Exception as e:
        print(f"Error obteniendo tablas: {e}")
    finally:
        if conn:
            conn.close()
    
    return tablas if tablas else ["2026_04", "2026_05", "grupos", "pb2"]

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route("/")
def index():
    tablas = obtener_tablas_disponibles()
    return render_template("index.html", tablas=tablas)

@app.route("/buscar", methods=["GET"])
def buscar():
    query = request.args.get("q", "").strip()
    tabla_bimestre = request.args.get("tabla", "").strip()

    tablas_validas = obtener_tablas_disponibles()
    if not tabla_bimestre or tabla_bimestre not in tablas_validas:
        tabla_bimestre = "2026_04" if "2026_04" in tablas_validas else tablas_validas[0]

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Si selecciona la misma tabla pb2, hacemos una consulta directa simple
        if tabla_bimestre.lower() == "pb2":
            cursor.execute('SELECT * FROM pb2 LIMIT 0;')
            cols_pb2 = [desc[0] for desc in cursor.description]

            if not query:
                sql = 'SELECT * FROM pb2 LIMIT 50;'
                cursor.execute(sql)
            else:
                palabras = query.split()
                condiciones = []
                params = []
                for w in palabras:
                    pat = f"%{w}%"
                    sub_c = [f'COALESCE("{c}"::text, \'\') ILIKE %s' for c in cols_pb2]
                    condiciones.append("(" + " OR ".join(sub_c) + ")")
                    params.extend([pat] * len(cols_pb2))

                sql = f'SELECT * FROM pb2 WHERE {" AND ".join(condiciones)} LIMIT 50;'
                cursor.execute(sql, tuple(params))

            rows = cursor.fetchall()
            cursor.close()

            resultados = []
            for r in rows:
                resultados.append({k: (str(v) if v is not None else "") for k, v in r.items()})

            return jsonify({"columnas": cols_pb2, "resultados": resultados, "tabla": tabla_bimestre})

        # LOGICA PRINCIPAL: CRUCE PB2 vs TABLA DE BIMESTRE
        # Detectar columnas clave de la tabla del bimestre seleccionado
        cursor.execute(f'SELECT * FROM "{tabla_bimestre}" LIMIT 0;')
        cols_bimestre = [desc[0] for desc in cursor.description] if cursor.description else []
        cols_lower = [c.lower() for c in cols_bimestre]

        col_mat_b = next((c for c in cols_bimestre if c.lower() == 'matricula'), cols_bimestre[0] if cols_bimestre else 'matricula')
        col_nom_b = next((c for c in cols_bimestre if c.lower() == 'nombre'), cols_bimestre[0] if cols_bimestre else 'nombre')

        # Búsqueda vinculada
        if not query:
            sql = f"""
                SELECT 
                    pb2.matricula AS matricula,
                    pb2.nombre AS nombre,
                    CASE 
                        WHEN b."{col_mat_b}" IS NOT NULL OR b."{col_nom_b}" IS NOT NULL THEN 'INSCRITO'
                        ELSE 'NO INSCRITO'
                    END AS estado_inscripcion,
                    b.*
                FROM pb2
                LEFT JOIN "{tabla_bimestre}" b 
                    ON LOWER(TRIM(COALESCE(pb2.matricula::text, ''))) = LOWER(TRIM(COALESCE(b."{col_mat_b}"::text, '')))
                    OR LOWER(TRIM(COALESCE(pb2.nombre::text, ''))) = LOWER(TRIM(COALESCE(b."{col_nom_b}"::text, '')))
                ORDER BY pb2.nombre ASC
                LIMIT 50;
            """
            cursor.execute(sql)
        else:
            palabras = query.split()
            condiciones = []
            params = []
            for w in palabras:
                pat = f"%{w}%"
                condiciones.append("(COALESCE(pb2.matricula::text, '') ILIKE %s OR COALESCE(pb2.nombre::text, '') ILIKE %s)")
                params.extend([pat, pat])

            where_sql = " AND ".join(condiciones)

            sql = f"""
                SELECT 
                    pb2.matricula AS matricula,
                    pb2.nombre AS nombre,
                    CASE 
                        WHEN b."{col_mat_b}" IS NOT NULL OR b."{col_nom_b}" IS NOT NULL THEN 'INSCRITO'
                        ELSE 'NO INSCRITO'
                    END AS estado_inscripcion,
                    b.*
                FROM pb2
                LEFT JOIN "{tabla_bimestre}" b 
                    ON LOWER(TRIM(COALESCE(pb2.matricula::text, ''))) = LOWER(TRIM(COALESCE(b."{col_mat_b}"::text, '')))
                    OR LOWER(TRIM(COALESCE(pb2.nombre::text, ''))) = LOWER(TRIM(COALESCE(b."{col_nom_b}"::text, '')))
                WHERE {where_sql}
                ORDER BY pb2.nombre ASC
                LIMIT 50;
            """
            cursor.execute(sql, tuple(params))

        rows = cursor.fetchall()

        # Organizar nombres de columnas eliminando duplicados
        columnas = []
        if cursor.description:
            vistas = set()
            for desc in cursor.description:
                c_name = desc[0]
                if c_name not in vistas:
                    columnas.append(c_name)
                    vistas.add(c_name)

        cursor.close()

        resultados = []
        for r in rows:
            resultados.append({k: (str(v) if v is not None else "") for k, v in r.items()})

        return jsonify({"columnas": columnas, "resultados": resultados, "tabla": tabla_bimestre})

    except Exception as e:
        print(f"ERROR EN POSTGRESQL: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
