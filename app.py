# -*- coding: utf-8 -*-
import os, csv, io, json, time, re, psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, Response, render_template

app = Flask(__name__)

DB_URI = "postgresql://neondb_owner:npg_uBxvgk0iyXK8@ep-fragrant-fog-b5cyavrb-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&connect_timeout=5"
TABLA_MAESTRA = "pb2"
TABLA_PROFESORES = "profesores"
TABLA_VEHICULAR = "acceso_vehicular"

PASSWORD_ADMIN = "celex2026"
PASSWORD_PREFECTURA = "pref26"

PASES_HOY = []
CREDENCIALES_HOY = []
PRESTAMOS_HOY = []
CORBATINES_HOY = []

def get_db():
    return psycopg2.connect(DB_URI, cursor_factory=RealDictCursor, connect_timeout=5)

def inicializar_tablas_sistema():
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Tabla Profesores
        cur.execute("""
            SELECT column_name FROM information_schema.columns WHERE table_name = 'profesores';
        """)
        cols_prof = [r['column_name'] for r in cur.fetchall()]
        if not cols_prof:
            cur.execute(f"CREATE TABLE {TABLA_PROFESORES} (nombre VARCHAR(255) PRIMARY KEY);")
        elif 'nombre' not in cols_prof:
            cur.execute(f"ALTER TABLE {TABLA_PROFESORES} ADD COLUMN nombre VARCHAR(255) UNIQUE;")

        # Tabla Acceso Vehicular (Módulo 5)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLA_VEHICULAR} (
                folio SERIAL PRIMARY KEY,
                matricula VARCHAR(50),
                nombre VARCHAR(255),
                periodo VARCHAR(100),
                tipo_vehiculo VARCHAR(50),
                marca VARCHAR(100),
                modelo VARCHAR(100),
                color VARCHAR(50),
                placas VARCHAR(50),
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error inicializando tablas: {e}")

inicializar_tablas_sistema()

def obtener_tablas():
    tablas = {}
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name NOT IN ('pb2', 'grupos', 'historial_credenciales_diario', 'profesores', 'acceso_vehicular') AND table_type = 'BASE TABLE';")
        for r in cur.fetchall():
            tablas[f"Periodo {r['table_name']}"] = r['table_name']
        conn.close()
    except Exception as e:
        print(f"Error tablas: {e}")
    return tablas if tablas else {"Periodo 2026_04": "2026_04"}

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route("/")
def index():
    return render_template("index.html", tablas=obtener_tablas())

# ==========================================
# AUTENTICACIÓN / LOGIN
# ==========================================

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    rol = data.get("rol", "").strip()
    pwd = data.get("password", "").strip()

    if rol == "admin":
        if pwd == PASSWORD_ADMIN:
            return jsonify({
                "success": True, 
                "rol": "admin", 
                "nombre": "Coord. Académica", 
                "modulos": ["m0", "m1", "m2", "m3", "m4", "m5"]
            })
        return jsonify({"success": False, "error": "Contraseña de Coord. Académica incorrecta"}), 401

    elif rol == "prefectura":
        if pwd == PASSWORD_PREFECTURA:
            return jsonify({
                "success": True, 
                "rol": "prefectura", 
                "nombre": "Prefectura", 
                "modulos": ["m0", "m2", "m4"]
            })
        return jsonify({"success": False, "error": "Contraseña de Prefectura incorrecta"}), 401

    elif rol == "prof_alum":
        return jsonify({
            "success": True, 
            "rol": "prof_alum", 
            "nombre": "Prof. y Alum.", 
            "modulos": ["m2", "m4"]
        })

    return jsonify({"success": False, "error": "Rol no válido"}), 400

# ==========================================
# MÓDULO 0: VERIFICACIÓN DE INSCRIPCIÓN
# ==========================================

@app.route("/api/m0/verificar")
def api_m0_verificar():
    q = request.args.get("q", "").strip()
    tabla_bimestre = request.args.get("tabla", "2026_04").strip()
    if not q:
        return jsonify({"resultados": []})
    
    palabras = [p for p in q.split() if p]
    try:
        conn = get_db()
        cur = conn.cursor()
        condiciones = []
        parametros = []
        
        for p in palabras:
            patron = f"%{p}%"
            condicion = """
                (TRANSLATE(LOWER(CAST(p.matricula AS VARCHAR)), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
                 OR TRANSLATE(LOWER(COALESCE(p.nombre, '')), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU'))
            """
            condiciones.append(condicion)
            parametros.extend([patron, patron])
        
        sql_where = " AND ".join(condiciones)
        
        sql = f"""
            SELECT 
                CAST(p.matricula AS VARCHAR) AS matricula,
                COALESCE(p.nombre, '')::text AS nombre,
                COALESCE(b.grupo, 'S/G')::text AS grupo,
                COALESCE(b.salon, 'S/S')::text AS salon,
                CASE WHEN b.matricula IS NOT NULL THEN TRUE ELSE FALSE END AS inscrito
            FROM {TABLA_MAESTRA} p
            LEFT JOIN "{tabla_bimestre}" b ON CAST(p.matricula AS VARCHAR) = CAST(b.matricula AS VARCHAR)
            WHERE {sql_where}
            LIMIT 30;
        """
        cur.execute(sql, tuple(parametros))
        r = cur.fetchall()
        conn.close()
        return jsonify({"resultados": r})
    except Exception as e:
        return jsonify({"resultados": [], "error": str(e)}), 500

# ==========================================
# MÓDULO 1: BÚSQUEDA INTEGRA E HISTORIAL
# ==========================================

@app.route("/api/m1/buscar")
def api_m1_buscar():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"resultados": []})
    
    palabras = [p for p in q.split() if p]
    try:
        conn = get_db()
        cur = conn.cursor()
        condiciones = []
        parametros = []
        
        for p in palabras:
            patron = f"%{p}%"
            condicion = """
                (TRANSLATE(LOWER(CAST(matricula AS VARCHAR)), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
                 OR TRANSLATE(LOWER(COALESCE(nombre, '')), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU'))
            """
            condiciones.append(condicion)
            parametros.extend([patron, patron])
        
        sql_where = " AND ".join(condiciones)
        sql = f"SELECT CAST(matricula AS VARCHAR) AS matricula, COALESCE(nombre, '')::text AS nombre FROM {TABLA_MAESTRA} WHERE {sql_where} LIMIT 30;"
        cur.execute(sql, tuple(parametros))
        r = cur.fetchall()
        conn.close()
        return jsonify({"resultados": r})
    except Exception as e:
        return jsonify({"resultados": [], "error": str(e)}), 500

@app.route("/api/m1/historial")
def api_m1_historial():
    mat = request.args.get("mat", "").strip()
    if not mat: 
        return jsonify({"historial": []})
    tablas = obtener_tablas()
    sq = []
    p = []
    for l, t in tablas.items():
        sq.append(f"SELECT '{l}'::text AS periodo, COALESCE(g.nivel, SPLIT_PART(b.grupo::text, '-', 1))::text AS nivel_cursado, COALESCE(b.grupo, 'S/G')::text AS grupo, COALESCE(b.turno, 'S/T')::text AS turno, COALESCE(b.calificacion, 0) AS calificacion FROM \"{t}\" b LEFT JOIN grupos g ON b.id_grupo = g.id_grupo WHERE CAST(b.matricula AS VARCHAR) = %s")
        p.append(mat)
    
    if not sq:
        return jsonify({"historial": []})

    conn = get_db()
    cur = conn.cursor()
    cur.execute(' UNION ALL '.join(sq) + ' ORDER BY periodo ASC;', tuple(p))
    r = cur.fetchall()
    conn.close()
    return jsonify({"historial": r})

@app.route("/api/m1/exportar")
def api_m1_exportar():
    mat = request.args.get("mat", "").strip()
    nom = request.args.get("nom", "").strip()
    tablas = obtener_tablas()
    sq = []
    p = []
    for l, t in tablas.items():
        sq.append(f"SELECT '{l}'::text AS periodo, COALESCE(g.nivel, SPLIT_PART(b.grupo::text, '-', 1))::text AS nivel_cursado, COALESCE(b.grupo, 'S/G')::text AS grupo, COALESCE(b.turno, 'S/T')::text AS turno, COALESCE(b.calificacion, 0) AS calificacion FROM \"{t}\" b LEFT JOIN grupos g ON b.id_grupo = g.id_grupo WHERE CAST(b.matricula AS VARCHAR) = %s")
        p.append(mat)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Matricula', 'Nombre del Alumno', 'Periodo', 'Nivel', 'Grupo', 'Turno', 'Calificacion'])
    
    if sq:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(' UNION ALL '.join(sq) + ' ORDER BY periodo ASC;', tuple(p))
        rows = cur.fetchall()
        conn.close()
        for r in rows:
            writer.writerow([mat, nom, r['periodo'], r['nivel_cursado'], r['grupo'], r['turno'], r['calificacion']])

    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename=Historial_{mat}.csv'})

# ==========================================
# MÓDULO 2: PASES DE SALIDA
# ==========================================

@app.route("/api/m2/buscar")
def api_m2_buscar():
    q = request.args.get("q", "").strip()
    t = request.args.get("tabla", "2026_04").strip()
    if not q: return jsonify({"resultados": []})
    
    palabras = [p for p in q.split() if p]
    conn = get_db()
    cur = conn.cursor()
    condiciones = []
    parametros = []
    for p in palabras:
        patron = f"%{p}%"
        condicion = """
            (TRANSLATE(LOWER(CAST(b.matricula AS VARCHAR)), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
             OR TRANSLATE(LOWER(COALESCE(p.nombre, '')), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU'))
        """
        condiciones.append(condicion)
        parametros.extend([patron, patron])
    
    sql_where = " AND ".join(condiciones)
    sql = f"SELECT CAST(b.matricula AS VARCHAR) AS matricula, COALESCE(p.nombre, 'ALUMNO REGISTRADO')::text AS nombre, COALESCE(b.grupo, 'S/G')::text AS grupo FROM \"{t}\" b LEFT JOIN pb2 p ON CAST(b.matricula AS VARCHAR) = CAST(p.matricula AS VARCHAR) WHERE {sql_where} LIMIT 20;"
    
    cur.execute(sql, tuple(parametros))
    r = cur.fetchall()
    conn.close()
    return jsonify({"resultados": r})

@app.route("/api/m2/pases/emitir", methods=["POST"])
def api_m2_pases_emitir():
    data = request.json or {}
    mat = data.get("matricula", "").strip()
    nom = data.get("nombre", "").strip()
    grupo = data.get("grupo", "S/G").strip()
    motivo = data.get("motivo", "Personal").strip()
    mayor_edad = data.get("mayor_edad", "No").strip()
    tipo_acceso = data.get("tipo_acceso", "Peatonal").strip()
    hora = time.strftime("%H:%M:%S")

    if not mat or not nom:
        return jsonify({"success": False, "error": "Datos incompletos"}), 400

    pase = {
        "hora": hora,
        "matricula": mat,
        "nom": nom,
        "grupo": grupo,
        "motivo": motivo,
        "mayor_edad": mayor_edad,
        "tipo_acceso": tipo_acceso
    }
    PASES_HOY.insert(0, pase)
    return jsonify({"success": True, "pase": pase})

@app.route("/api/m2/pases/limpiar", methods=["POST"])
def api_m2_pases_limpiar():
    data = request.json or {}
    pwd = data.get("password", "").strip()
    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 403

    global PASES_HOY
    PASES_HOY = []
    return jsonify({"success": True})

@app.route("/api/m2/exportar_pases")
def api_m2_exportar_pases():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Hora', 'Matricula', 'Nombre del Alumno', 'Grupo', 'Mayor de Edad', 'Tipo de Acceso', 'Motivo'])
    for p in PASES_HOY:
        writer.writerow([p['hora'], p['matricula'], p['nom'], p.get('grupo', 'S/G'), p.get('mayor_edad', 'No'), p.get('tipo_acceso', 'Peatonal'), p['motivo']])

    output.seek(0)
    fecha_hoy = time.strftime("%Y%m%d")
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename=Pases_Salida_{fecha_hoy}.csv'})

@app.route("/api/m2/pases/stream")
def api_m2_pases_stream():
    def event_stream():
        ultimo_conteo = -1
        while True:
            actual = len(PASES_HOY)
            if actual != ultimo_conteo:
                data = json.dumps({"pases": PASES_HOY})
                yield f"data: {data}\n\n"
                ultimo_conteo = actual
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")

# ==========================================
# MÓDULO 3: CREDENCIALIZACIÓN Y GENERACIÓN SVG
# ==========================================

@app.route("/api/m3/buscar")
def api_m3_buscar():
    q = request.args.get("q", "").strip()
    t = request.args.get("tabla", "2026_04").strip()
    if not q: return jsonify({"resultados": []})
    
    palabras = [p for p in q.split() if p]
    conn = get_db()
    cur = conn.cursor()
    condiciones = []
    parametros = []
    for p in palabras:
        patron = f"%{p}%"
        condicion = """
            (TRANSLATE(LOWER(CAST(b.matricula AS VARCHAR)), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
             OR TRANSLATE(LOWER(COALESCE(p.nombre, '')), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU'))
        """
        condiciones.append(condicion)
        parametros.extend([patron, patron])
    
    sql_where = " AND ".join(condiciones)
    sql = f"SELECT CAST(b.matricula AS VARCHAR) AS matricula, COALESCE(p.nombre, 'ALUMNO REGISTRADO')::text AS nombre, COALESCE(b.grupo, 'S/G')::text AS grupo, COALESCE(b.salon, 'S/S')::text AS salon FROM \"{t}\" b LEFT JOIN pb2 p ON CAST(b.matricula AS VARCHAR) = CAST(p.matricula AS VARCHAR) WHERE {sql_where} LIMIT 20;"
    
    cur.execute(sql, tuple(parametros))
    r = cur.fetchall()
    conn.close()
    return jsonify({"resultados": r})

@app.route("/api/m3/credencial/solicitar", methods=["POST"])
def api_m3_credencial_solicitar():
    data = request.json or {}
    mat_original = data.get("matricula_original", "").strip()
    mat = data.get("matricula", "").strip()
    nom = data.get("nombre", "").strip()
    grupo = data.get("grupo", "S/G").strip()
    salon = data.get("salon", "S/S").strip()
    turno = data.get("turno", "matutino").strip()
    px = data.get("px", 20)
    py = data.get("py", 380)
    sc = data.get("sc", 1.0)
    tabla = data.get("tabla", "2026_04").strip()
    hora = time.strftime("%H:%M:%S")

    if not mat or not nom:
        return jsonify({"success": False, "error": "Datos incompletos"}), 400

    mat_referencia = mat_original if mat_original else mat

    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(
            f"UPDATE {TABLA_MAESTRA} SET matricula = %s, nombre = %s WHERE CAST(matricula AS VARCHAR) = %s;",
            (mat, nom, mat_referencia)
        )
        
        cur.execute(
            f"UPDATE \"{tabla}\" SET matricula = %s, salon = %s WHERE CAST(matricula AS VARCHAR) = %s;",
            (mat, salon, mat_referencia)
        )
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error actualizando BD de origen: {e}")

    existente = False
    for item in CREDENCIALES_HOY:
        if item["matricula"] == mat_referencia or item["matricula"] == mat:
            item["matricula"] = mat
            item["nom"] = nom
            item["grupo"] = grupo
            item["salon"] = salon
            item["turno"] = turno
            item["px"] = px
            item["py"] = py
            item["sc"] = sc
            item["hora"] = hora
            existente = True
            break

    if not existente:
        item = {
            "hora": hora,
            "matricula": mat,
            "nom": nom,
            "grupo": grupo,
            "salon": salon,
            "turno": turno,
            "px": px,
            "py": py,
            "sc": sc
        }
        CREDENCIALES_HOY.insert(0, item)

    return jsonify({"success": True})

@app.route("/api/m3/credencial/stream")
def api_m3_credencial_stream():
    def event_stream():
        ultimo_conteo = -1
        while True:
            actual = len(CREDENCIALES_HOY)
            if actual != ultimo_conteo:
                data = json.dumps({"credenciales": CREDENCIALES_HOY})
                yield f"data: {data}\n\n"
                ultimo_conteo = actual
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/m3/credencial/limpiar", methods=["POST"])
def api_m3_credencial_limpiar():
    data = request.json or {}
    pwd = data.get("password", "").strip()
    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 403

    global CREDENCIALES_HOY
    CREDENCIALES_HOY = []
    return jsonify({"success": True})

@app.route("/api/m3/credencial/eliminar", methods=["POST"])
def api_m3_credencial_eliminar():
    data = request.json or {}
    mat = data.get("matricula", "").strip()
    global CREDENCIALES_HOY
    CREDENCIALES_HOY = [c for c in CREDENCIALES_HOY if c["matricula"] != mat]
    return jsonify({"success": True})

@app.route("/api/m3/credencial/svg")
def api_m3_credencial_svg():
    mat = request.args.get("mat", "").strip()
    nom = request.args.get("nom", "NOMBRE ALUMNO").strip()
    turno = request.args.get("turno", "matutino").strip().lower()

    try:
        px = float(request.args.get("px", 20))
        py = float(request.args.get("py", 380))
        sc = float(request.args.get("sc", 1.0))
    except Exception:
        px, py, sc = 20.0, 380.0, 1.0

    nombre_archivo = "Formato credencial VESP nueva.svg" if "vesp" in turno else "Formato credencial MATUTINO nueva.svg"
    
    svg_content = ""
    for carpeta in ["templates", "static", "."]:
        ruta = os.path.join(app.root_path, carpeta, nombre_archivo)
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                svg_content = f.read()
            break

    if svg_content:
        l_nom = len(nom)
        f_size = "9px" if l_nom > 35 else ("11px" if l_nom > 25 else ("12px" if l_nom > 18 else "14px"))
        nom_formateado = f'<tspan font-size="{f_size}" font-weight="bold" textLength="140" lengthAdjust="spacingAndGlyphs">{nom}</tspan>'
        
        svg_content = svg_content.replace("{{NOMBRE}}", nom_formateado).replace("{{MATRICULA}}", mat)

        svg_content = re.sub(r'<text[^>]*>(?:(?!</text>).)*capa_codigo_barras(?:(?!</text>).)*</text>', '', svg_content, flags=re.DOTALL)
        svg_content = re.sub(r'<g[^>]*>(?:(?!</g>).)*capa_codigo_barras(?:(?!</g>).)*</g>', '', svg_content, flags=re.DOTALL)
        svg_content = svg_content.replace('<g id="capa_codigo_barras"></g>', '')
        svg_content = svg_content.replace('&lt;g id="capa_codigo_barras"&gt;&lt;/g&gt;', '')

        barras = []
        x_curr = 15
        
        for ch in str(mat):
            val = ord(ch)
            w1 = 2.5 if val % 2 == 0 else 4.0
            w2 = 1.5 if val % 3 == 0 else 2.5
            barras.append(f'<rect x="{x_curr:.1f}" y="0" width="{w1:.1f}" height="28" fill="#000000"/>')
            x_curr += w1 + w2

        ancho_caja = x_curr + 15
        
        cb_overlay = f'''
        <g id="capa_cb_definitiva" transform="translate({px}, {py}) rotate(-90) scale({sc})">
            <rect x="0" y="-4" width="{ancho_caja:.1f}" height="42" fill="#FFFFFF" stroke="#000000" stroke-width="1" rx="2"/>
            {''.join(barras)}
            <text x="{ancho_caja/2:.1f}" y="36" font-family="Arial, Helvetica, sans-serif" font-size="9" font-weight="bold" text-anchor="middle" fill="#000000">{mat}</text>
        </g>
        '''

        if "</svg>" in svg_content:
            svg_content = svg_content.replace("</svg>", f"{cb_overlay}</svg>")

        return Response(svg_content, mimetype="image/svg+xml")
    else:
        return Response(f"<svg xmlns='http://www.w3.org/2000/svg' width='400' height='600'><text x='20' y='50' fill='red'>No se encontró {nombre_archivo}</text></svg>", mimetype="image/svg+xml")

# ==========================================
# MÓDULO 4: PRÉSTAMO DE MATERIALES
# ==========================================

@app.route("/api/m4/profesores", methods=["GET"])
def api_m4_profesores_listar():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"SELECT nombre FROM {TABLA_PROFESORES} ORDER BY nombre ASC;")
        profs = [r["nombre"] for r in cur.fetchall()]
        conn.close()
        return jsonify({"profesores": profs})
    except Exception as e:
        return jsonify({"profesores": [], "error": str(e)}), 500

@app.route("/api/m4/profesores/guardar", methods=["POST"])
def api_m4_profesores_guardar():
    data = request.json or {}
    pwd = data.get("password", "").strip()
    nombre_ant = data.get("nombre_anterior", "").strip()
    nombre_nue = data.get("nombre_nuevo", "").strip()

    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña de administrador incorrecta"}), 403

    if not nombre_nue:
        return jsonify({"success": False, "error": "El nombre no puede estar vacío"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        if nombre_ant:
            cur.execute(f"UPDATE {TABLA_PROFESORES} SET nombre = %s WHERE nombre = %s;", (nombre_nue, nombre_ant))
        else:
            cur.execute(f"INSERT INTO {TABLA_PROFESORES} (nombre) VALUES (%s) ON CONFLICT DO NOTHING;", (nombre_nue,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/m4/prestamo/registrar", methods=["POST"])
def api_m4_prestamo_registrar():
    data = request.json or {}
    id_prestamo = data.get("id_prestamo")
    profesor = data.get("profesor", "").strip()
    articulos = data.get("articulos", [])
    hora = time.strftime("%H:%M:%S")

    if not profesor or not articulos:
        return jsonify({"success": False, "error": "Selecciona un profesor y al menos un artículo"}), 400

    if id_prestamo is not None:
        for p in PRESTAMOS_HOY:
            if p["id"] == id_prestamo:
                p["profesor"] = profesor
                p["articulos"] = articulos
                break
    else:
        nuevo_id = int(time.time() * 1000)
        p = {
            "id": nuevo_id,
            "hora": hora,
            "profesor": profesor,
            "articulos": articulos,
            "estado": "MATERIAL EN USO"
        }
        PRESTAMOS_HOY.insert(0, p)

    return jsonify({"success": True})

@app.route("/api/m4/prestamo/devolver", methods=["POST"])
def api_m4_prestamo_devolver():
    data = request.json or {}
    id_p = data.get("id")
    for p in PRESTAMOS_HOY:
        if p["id"] == id_p:
            p["estado"] = "ENTREGADO"
            break
    return jsonify({"success": True})

@app.route("/api/m4/prestamo/limpiar", methods=["POST"])
def api_m4_prestamo_limpiar():
    data = request.json or {}
    pwd = data.get("password", "").strip()
    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 403

    global PRESTAMOS_HOY
    PRESTAMOS_HOY = []
    return jsonify({"success": True})

@app.route("/api/m4/prestamo/stream")
def api_m4_prestamo_stream():
    def event_stream():
        ultimo_hash = ""
        while True:
            actual_str = json.dumps(PRESTAMOS_HOY)
            if actual_str != ultimo_hash:
                yield f"data: {actual_str}\n\n"
                ultimo_hash = actual_str
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")

# ==========================================
# MÓDULO 5: CORBATINES DE ACCESO VEHICULAR
# ==========================================

@app.route("/api/m5/buscar_alumno")
def api_m5_buscar_alumno():
    q = request.args.get("q", "").strip()
    t = request.args.get("tabla", "2026_04").strip()
    if not q: return jsonify({"resultados": []})
    
    palabras = [p for p in q.split() if p]
    conn = get_db()
    cur = conn.cursor()
    condiciones = []
    parametros = []
    for p in palabras:
        patron = f"%{p}%"
        condicion = """
            (TRANSLATE(LOWER(CAST(b.matricula AS VARCHAR)), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU')
             OR TRANSLATE(LOWER(COALESCE(p.nombre, '')), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU') LIKE TRANSLATE(LOWER(%s), 'áéíóúÁÉÍÓÚ', 'aeiouAEIOU'))
        """
        condiciones.append(condicion)
        parametros.extend([patron, patron])
    
    sql_where = " AND ".join(condiciones)
    sql = f"SELECT CAST(b.matricula AS VARCHAR) AS matricula, COALESCE(p.nombre, 'ALUMNO REGISTRADO')::text AS nombre FROM \"{t}\" b LEFT JOIN pb2 p ON CAST(b.matricula AS VARCHAR) = CAST(p.matricula AS VARCHAR) WHERE {sql_where} LIMIT 15;"
    
    cur.execute(sql, tuple(parametros))
    r = cur.fetchall()
    conn.close()
    return jsonify({"resultados": r})

@app.route("/api/m5/siguiente_folio")
def api_m5_siguiente_folio():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"SELECT COALESCE(MAX(folio), 0) + 1 AS sig FROM {TABLA_VEHICULAR};")
        sig = cur.fetchone()['sig']
        conn.close()
        return jsonify({"siguiente_folio": sig})
    except Exception as e:
        return jsonify({"siguiente_folio": 1, "error": str(e)})

@app.route("/api/m5/listar_registros")
def api_m5_listar_registros():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"SELECT folio, matricula, nombre, periodo, tipo_vehiculo, marca, modelo, color, placas, TO_CHAR(fecha_registro, 'YYYY-MM-DD HH24:MI') as fecha FROM {TABLA_VEHICULAR} ORDER BY folio DESC;")
        rows = cur.fetchall()
        conn.close()
        return jsonify({"registros": rows})
    except Exception as e:
        return jsonify({"registros": [], "error": str(e)}), 500

@app.route("/api/m5/guardar", methods=["POST"])
def api_m5_guardar():
    data = request.json or {}
    folio = data.get("folio")
    mat = data.get("matricula", "").strip()
    nom = data.get("nombre", "").strip()
    periodo = data.get("periodo", "2026_04").strip()
    tipo = data.get("tipo_vehiculo", "Auto").strip()
    marca = data.get("marca", "").strip()
    modelo = data.get("modelo", "").strip()
    color = data.get("color", "").strip()
    placas = data.get("placas", "").strip().upper()
    hora = time.strftime("%H:%M:%S")

    if not mat or not nom or not placas:
        return jsonify({"success": False, "error": "Completa todos los campos del vehículo"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        
        existe = False
        if folio:
            cur.execute(f"SELECT folio FROM {TABLA_VEHICULAR} WHERE folio = %s;", (folio,))
            existe = cur.fetchone() is not None

        if existe:
            cur.execute(
                f"UPDATE {TABLA_VEHICULAR} SET matricula=%s, nombre=%s, periodo=%s, tipo_vehiculo=%s, marca=%s, modelo=%s, color=%s, placas=%s WHERE folio=%s;",
                (mat, nom, periodo, tipo, marca, modelo, color, placas, folio)
            )
            folio_num = int(folio)
        else:
            if folio:
                cur.execute(
                    f"INSERT INTO {TABLA_VEHICULAR} (folio, matricula, nombre, periodo, tipo_vehiculo, marca, modelo, color, placas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING folio;",
                    (folio, mat, nom, periodo, tipo, marca, modelo, color, placas)
                )
                folio_num = cur.fetchone()['folio']
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{TABLA_VEHICULAR}', 'folio'), (SELECT MAX(folio) FROM {TABLA_VEHICULAR}));")
            else:
                cur.execute(
                    f"INSERT INTO {TABLA_VEHICULAR} (matricula, nombre, periodo, tipo_vehiculo, marca, modelo, color, placas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING folio;",
                    (mat, nom, periodo, tipo, marca, modelo, color, placas)
                )
                folio_num = cur.fetchone()['folio']

        conn.commit()
        conn.close()

        registro_memoria = {
            "folio": folio_num,
            "hora": hora,
            "matricula": mat,
            "nom": nom,
            "periodo": periodo,
            "tipo_vehiculo": tipo,
            "marca": marca,
            "modelo": modelo,
            "color": color,
            "placas": placas
        }

        global CORBATINES_HOY
        CORBATINES_HOY = [c for c in CORBATINES_HOY if c["folio"] != folio_num]
        CORBATINES_HOY.insert(0, registro_memoria)

        return jsonify({"success": True, "folio": folio_num})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/m5/reiniciar_secuencia", methods=["POST"])
def api_m5_reiniciar_secuencia():
    data = request.json or {}
    pwd = data.get("password", "").strip()
    nuevo_inicio = int(data.get("nuevo_inicio", 1))

    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña de administrador incorrecta"}), 403

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{TABLA_VEHICULAR}', 'folio'), {nuevo_inicio}, false);")
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/m5/borrar_todo", methods=["POST"])
def api_m5_borrar_todo():
    data = request.json or {}
    pwd = data.get("password", "").strip()

    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña de administrador incorrecta"}), 403

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"TRUNCATE TABLE {TABLA_VEHICULAR} RESTART IDENTITY;")
        conn.commit()
        conn.close()

        global CORBATINES_HOY
        CORBATINES_HOY = []

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/m5/eliminar", methods=["POST"])
def api_m5_eliminar():
    data = request.json or {}
    folio = data.get("folio")
    pwd = data.get("password", "").strip()

    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña de administrador incorrecta"}), 403

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {TABLA_VEHICULAR} WHERE folio = %s;", (folio,))
        conn.commit()
        conn.close()

        global CORBATINES_HOY
        CORBATINES_HOY = [c for c in CORBATINES_HOY if c["folio"] != folio]
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/m5/limpiar_sesion", methods=["POST"])
def api_m5_limpiar_sesion():
    data = request.json or {}
    pwd = data.get("password", "").strip()

    if pwd != PASSWORD_ADMIN:
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 403

    global CORBATINES_HOY
    CORBATINES_HOY = []
    return jsonify({"success": True})

@app.route("/api/m5/stream")
def api_m5_stream():
    def event_stream():
        ultimo_hash = ""
        while True:
            actual_str = json.dumps(CORBATINES_HOY)
            if actual_str != ultimo_hash:
                yield f"data: {actual_str}\n\n"
                ultimo_hash = actual_str
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/m5/corbatin/svg")
def api_m5_corbatin_svg():
    folio = str(request.args.get("folio", "0000")).zfill(4)
    mat = request.args.get("mat", "").strip()
    nom = request.args.get("nom", "").strip()
    periodo = request.args.get("periodo", "").strip()
    tipo = request.args.get("tipo", "AUTO").strip()
    marca = request.args.get("marca", "").strip()
    modelo = request.args.get("modelo", "").strip()
    color = request.args.get("color", "").strip()
    placas = request.args.get("placas", "").strip()

    nombre_archivo = "Formato corbatin.svg"
    svg_content = ""

    for carpeta in ["templates", "static", "."]:
        ruta = os.path.join(app.root_path, carpeta, nombre_archivo)
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                svg_content = f.read()
            break

    if svg_content:
        svg_content = svg_content.replace("{{FOLIO}}", f"#{folio}")
        svg_content = svg_content.replace("{{NOMBRE}}", nom)
        svg_content = svg_content.replace("{{MATRICULA}}", mat)
        svg_content = svg_content.replace("{{PERIODO}}", periodo)
        svg_content = svg_content.replace("{{TIPO}}", tipo)
        svg_content = svg_content.replace("{{MARCA}}", marca)
        svg_content = svg_content.replace("{{MODELO}}", modelo)
        svg_content = svg_content.replace("{{COLOR}}", color)
        svg_content = svg_content.replace("{{PLACAS}}", placas)

        svg_content = re.sub(
            r'<svg[^>]*>', 
            '<svg xmlns="http://www.w3.org/2000/svg" width="4in" height="6in" viewBox="0 0 100.1 152" preserveAspectRatio="none">', 
            svg_content, 
            count=1
        )

        return Response(svg_content, mimetype="image/svg+xml")
    else:
        return Response(
            f"<svg xmlns='http://www.w3.org/2000/svg' width='4in' height='6in' viewBox='0 0 100.1 152'><text x='10' y='20' fill='red'>No se encontró {nombre_archivo}</text></svg>", 
            mimetype="image/svg+xml"
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)