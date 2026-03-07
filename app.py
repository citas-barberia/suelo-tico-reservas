import csv
from io import StringIO
from flask import Response, Flask, render_template, request, redirect, url_for, jsonify, session
import json
import os
from datetime import datetime, date
from urllib.parse import quote_plus

app = Flask(__name__)

# ==========================
# CONFIGURACIÓN SEGURA (ENV)
# ==========================
app.secret_key = os.getenv("APP_SECRET_KEY", "dev-secret-cambiar-antes-de-produccion")

ARCHIVO_RESERVAS = "reservas.txt"
ARCHIVO_EVENTOS = "eventos.txt"

# RETOS
ARCHIVO_RETOS = "retos.txt"
ARCHIVO_SOLICITUDES_RETOS = "solicitudes_retos.txt"

# DATOS DEL NEGOCIO
DUENO_NOMBRE = "Suelo Tico"
DUENO_TELEFONO = "50688888888"  # WhatsApp sin + ni espacios
NUMERO_SINPE = "8888-8888"

# LOGIN ADMIN
ADMIN_USUARIO = os.getenv("ADMIN_USUARIO", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

CANCHAS = [
    {"id": 1, "nombre": "Cancha 1", "tipo": "Fútbol 5"},
    {"id": 2, "nombre": "Cancha 2", "tipo": "Fútbol 7"},
    {"id": 3, "nombre": "Cancha 3", "tipo": "Fútbol 5"},
]

HORARIOS = [
    "9am", "10am", "11am",
    "12pm", "1pm", "2pm", "3pm", "4pm", "5pm",
    "6pm", "7pm", "8pm", "9pm", "10pm"
]

# ==========================
# UTILIDADES JSON
# ==========================
def leer_json_lista(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        contenido = f.read().strip()
        if not contenido:
            return []
        try:
            return json.loads(contenido)
        except json.JSONDecodeError:
            return []

def guardar_json_lista(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def siguiente_id(lista):
    if not lista:
        return 1
    return max(int(x.get("id", 0)) for x in lista) + 1

# ==========================
# RESERVAS
# ==========================
def leer_reservas():
    reservas = leer_json_lista(ARCHIVO_RESERVAS)
    for r in reservas:
        if "pagado" not in r:
            r["pagado"] = False
        if "sinpe_reportado_cliente" not in r:
            r["sinpe_reportado_cliente"] = False
        if "estado" not in r:
            r["estado"] = "Reservada"
        if "monto" not in r:
            r["monto"] = 0
        if "origen" not in r:
            r["origen"] = "Reserva"
    return reservas

def guardar_reservas(reservas):
    guardar_json_lista(ARCHIVO_RESERVAS, reservas)

def leer_eventos():
    eventos = leer_json_lista(ARCHIVO_EVENTOS)
    eventos.sort(key=lambda e: e.get("fecha_evento", ""), reverse=True)
    return eventos

def guardar_eventos(eventos):
    guardar_json_lista(ARCHIVO_EVENTOS, eventos)

def formatear_fecha_latina(fecha_iso):
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        return f"{dt.day}/{dt.month}/{dt.year}"
    except Exception:
        return fecha_iso

def fecha_hoy_iso():
    return date.today().isoformat()

def parse_fecha_segura(fecha_iso):
    try:
        return datetime.strptime(fecha_iso, "%Y-%m-%d").date()
    except Exception:
        return None

def es_fecha_pasada(fecha_iso):
    try:
        fecha_reserva = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
        return fecha_reserva < date.today()
    except ValueError:
        return True

def hora_a_orden(hora_texto):
    if not hora_texto:
        return 9999
    h = str(hora_texto).strip().lower().replace(" ", "")
    h = h.replace(":00", "")
    try:
        if h.endswith("am") or h.endswith("pm"):
            sufijo = h[-2:]
            numero = int(h[:-2])
            if sufijo == "am":
                return 0 if numero == 12 else numero
            else:
                return 12 if numero == 12 else numero + 12
    except Exception:
        pass
    return 9999

def hora_ya_paso_para_hoy(fecha_iso, hora_texto):
    try:
        if fecha_iso != date.today().isoformat():
            return False
        orden = hora_a_orden(hora_texto)
        if orden == 9999:
            return True
        ahora = datetime.now()
        inicio_slot = ahora.replace(hour=orden, minute=0, second=0, microsecond=0)
        return ahora >= inicio_slot
    except Exception:
        return True

def obtener_precio_por_hora(hora):
    h = str(hora).strip().lower()
    horario_20000 = {"9am", "10am", "11am", "12pm", "1pm", "2pm", "3pm", "4pm", "5pm"}
    horario_25000 = {"6pm", "7pm", "8pm", "9pm", "10pm"}
    if h in horario_20000:
        return 20000
    if h in horario_25000:
        return 25000
    return 25000

# ==========================
# RETOS
# ==========================
def leer_retos():
    retos = leer_json_lista(ARCHIVO_RETOS)
    for r in retos:
        if "estado" not in r:
            r["estado"] = "Activo"
        if "cupo" not in r:
            r["cupo"] = 10
        if "precio" not in r:
            r["precio"] = 0
        if "descripcion" not in r:
            r["descripcion"] = ""
    return retos

def guardar_retos(retos):
    guardar_json_lista(ARCHIVO_RETOS, retos)

def leer_solicitudes_retos():
    sol = leer_json_lista(ARCHIVO_SOLICITUDES_RETOS)
    for s in sol:
        if "estado" not in s:
            s["estado"] = "Pendiente"
        if "nota" not in s:
            s["nota"] = ""
        if "tipo" not in s:
            s["tipo"] = "Publicado"
    return sol

def guardar_solicitudes_retos(sol):
    guardar_json_lista(ARCHIVO_SOLICITUDES_RETOS, sol)

def normalizar_tel(tel):
    return "".join(ch for ch in str(tel) if ch.isdigit())

def tel_a_wa(tel):
    dig = normalizar_tel(tel)
    if len(dig) == 8:
        return "506" + dig
    return dig

def wa_link(tel, texto):
    return f"https://wa.me/{tel_a_wa(tel)}?text={quote_plus(texto)}"

def reto_ya_paso(fecha_iso, hora_texto):
    f = parse_fecha_segura(fecha_iso)
    if not f:
        return True
    hoy = date.today()
    if f < hoy:
        return True
    if f > hoy:
        return False
    orden = hora_a_orden(hora_texto)
    if orden == 9999:
        return True
    ahora = datetime.now()
    inicio = ahora.replace(hour=orden, minute=0, second=0, microsecond=0)
    return ahora >= inicio

def autocerrar_retos():
    retos = leer_retos()
    cambio = False
    for r in retos:
        if r.get("estado") == "Activo" and reto_ya_paso(r.get("fecha", ""), r.get("hora", "")):
            r["estado"] = "Cerrado"
            r["fecha_cierre_auto"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cambio = True
    if cambio:
        guardar_retos(retos)

# ==========================
# DISPONIBILIDAD COMPARTIDA
# ==========================
def reto_ocupa_slot(fecha, cancha_id, hora):
    retos = leer_retos()
    for r in retos:
        if (
            r.get("estado") == "Activo"
            and r.get("fecha") == fecha
            and int(r.get("cancha_id", 0)) == int(cancha_id)
            and str(r.get("hora", "")).lower() == str(hora).lower()
        ):
            return True
    return False

def horario_ocupado(fecha, cancha_id, hora):
    reservas = leer_reservas()
    for r in reservas:
        if (
            r.get("fecha") == fecha
            and int(r.get("cancha_id")) == int(cancha_id)
            and str(r.get("hora", "")).lower() == str(hora).lower()
            and r.get("estado") == "Reservada"
        ):
            return True

    if reto_ocupa_slot(fecha, cancha_id, hora):
        return True

    return False

def obtener_horas_ocupadas(fecha, cancha_id):
    ocupadas = set()

    reservas = leer_reservas()
    for r in reservas:
        if (
            r.get("fecha") == fecha
            and int(r.get("cancha_id")) == int(cancha_id)
            and r.get("estado") == "Reservada"
        ):
            ocupadas.add(str(r.get("hora", "")).lower())

    retos = leer_retos()
    for rt in retos:
        if (
            rt.get("estado") == "Activo"
            and rt.get("fecha") == fecha
            and int(rt.get("cancha_id", 0)) == int(cancha_id)
        ):
            ocupadas.add(str(rt.get("hora", "")).lower())

    return list(ocupadas)

def obtener_horas_disponibles(fecha, cancha_id):
    if not fecha:
        return HORARIOS[:]

    horarios_base = [h for h in HORARIOS if not hora_ya_paso_para_hoy(fecha, h)]

    if not cancha_id:
        return horarios_base

    ocupadas = set(h.lower() for h in obtener_horas_ocupadas(fecha, cancha_id))
    return [h for h in horarios_base if h.lower() not in ocupadas]

def _filtrar_reservas(reservas, fecha_filtro="", cancha_filtro="", busqueda=""):
    resultado = reservas[:]
    if fecha_filtro:
        resultado = [r for r in resultado if r.get("fecha") == fecha_filtro]
    if cancha_filtro:
        try:
            resultado = [r for r in resultado if int(r.get("cancha_id", 0)) == int(cancha_filtro)]
        except ValueError:
            pass
    if busqueda:
        q = busqueda.strip().lower()
        resultado = [
            r for r in resultado
            if q in str(r.get("nombre", "")).lower()
            or q in str(r.get("telefono", "")).lower()
        ]
    return resultado

def registrar_evento(tipo, reserva):
    eventos = leer_json_lista(ARCHIVO_EVENTOS)
    ahora = datetime.now()

    if tipo == "reserva":
        mensaje = (
            f"✅ Reserva: {reserva.get('nombre')} agendó {reserva.get('cancha_nombre')} "
            f"para {formatear_fecha_latina(reserva.get('fecha', ''))} a las {reserva.get('hora')}"
        )
    elif tipo == "cancelacion":
        mensaje = (
            f"❌ Cancelación: {reserva.get('nombre')} canceló {reserva.get('cancha_nombre')} "
            f"del {formatear_fecha_latina(reserva.get('fecha', ''))} a las {reserva.get('hora')}"
        )
    else:
        mensaje = (
            f"💰 Pago confirmado: {reserva.get('nombre')} - {reserva.get('cancha_nombre')} "
            f"{formatear_fecha_latina(reserva.get('fecha', ''))} {reserva.get('hora')}"
        )

    evento = {
        "id": (max([int(e.get("id", 0)) for e in eventos], default=0) + 1),
        "tipo": tipo,
        "fecha_evento": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "fecha_evento_latina": f"{ahora.day}/{ahora.month}/{ahora.year} {ahora.strftime('%I:%M %p')}".lower(),
        "mensaje": mensaje,
        "cliente_nombre": reserva.get("nombre"),
        "cliente_telefono": reserva.get("telefono"),
        "cancha_nombre": reserva.get("cancha_nombre"),
        "cancha_tipo": reserva.get("cancha_tipo"),
        "fecha_reserva": reserva.get("fecha"),
        "hora": reserva.get("hora"),
        "metodo_pago": reserva.get("metodo_pago"),
        "monto": reserva.get("monto", 0),
    }
    eventos.append(evento)
    guardar_eventos(eventos)

def crear_reserva_desde_reto(fecha, hora, cancha_id, nombre, telefono, metodo_pago, monto, nota, origen="Reto", reto_id=None):
    if horario_ocupado(fecha, cancha_id, hora):
        return None, "Esa hora ya está ocupada en esa cancha."

    cancha_info = next((c for c in CANCHAS if int(c["id"]) == int(cancha_id)), None)
    if not cancha_info:
        return None, "Cancha inválida."

    reservas = leer_reservas()
    nueva = {
        "id": (max([int(r.get("id", 0)) for r in reservas], default=0) + 1),
        "nombre": nombre,
        "telefono": telefono,
        "fecha": fecha,
        "cancha_id": int(cancha_id),
        "cancha_nombre": cancha_info["nombre"],
        "cancha_tipo": cancha_info["tipo"],
        "hora": str(hora).lower(),
        "monto": int(monto),
        "metodo_pago": metodo_pago,
        "pagado": False,
        "sinpe_reportado_cliente": False,
        "estado": "Reservada",
        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "origen": origen,
        "nota_reto": nota or ""
    }
    if reto_id is not None:
        nueva["reto_id"] = int(reto_id)

    reservas.append(nueva)
    guardar_reservas(reservas)
    registrar_evento("reserva", nueva)
    return nueva, ""

# ==========================
# AUTH ADMIN
# ==========================
def admin_requerido():
    return session.get("admin_logueado") is True

def parse_bool_env(value, default=False):
    if value is None:
        return default
    v = str(value).strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default

def advertencias_seguridad_inicio():
    if app.secret_key == "dev-secret-cambiar-antes-de-produccion":
        print("⚠️ ADVERTENCIA: APP_SECRET_KEY por defecto (solo desarrollo).")
    if ADMIN_USUARIO == "admin" and ADMIN_PASSWORD == "1234":
        print("⚠️ ADVERTENCIA: ADMIN_USUARIO / ADMIN_PASSWORD por defecto.")

# ==========================
# FILTROS JINJA
# ==========================
@app.template_filter("fecha_latina")
def fecha_latina_filter(fecha_iso):
    return formatear_fecha_latina(fecha_iso)

@app.template_filter("colones")
def colones_filter(monto):
    try:
        monto_int = int(monto)
        return f"₡{monto_int:,}".replace(",", ".")
    except Exception:
        return f"₡{monto}"

@app.template_filter("fecha_larga")
def fecha_larga_filter(fecha_iso):
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        dias = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
        dia_sem = dias[dt.weekday()]
        return f"{dia_sem} {dt.day} de {meses[dt.month-1]}"
    except Exception:
        return fecha_iso

# ==========================
# CLIENTE: RESERVAS
# ==========================
@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    tipo_mensaje = ""
    reserva_creada = None

    fecha_sel = request.form.get("fecha", fecha_hoy_iso()) if request.method == "POST" else fecha_hoy_iso()
    cancha_sel = request.form.get("cancha_id", "") if request.method == "POST" else ""

    horas_disponibles = obtener_horas_disponibles(fecha_sel, cancha_sel) if cancha_sel else obtener_horas_disponibles(fecha_sel, "")

    whatsapp_link = ""
    wa_confirm_link = ""
    texto_confirm = ""

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        fecha = request.form.get("fecha", "").strip()
        cancha_id = request.form.get("cancha_id", "").strip()
        hora = request.form.get("hora", "").strip().lower()
        metodo_pago = request.form.get("metodo_pago", "").strip()

        horas_disponibles = obtener_horas_disponibles(fecha, cancha_id) if cancha_id else obtener_horas_disponibles(fecha, "")
        fecha_sel = fecha
        cancha_sel = cancha_id

        if not nombre or not telefono or not fecha or not cancha_id or not hora or not metodo_pago:
            mensaje = "Por favor completa todos los campos."
            tipo_mensaje = "error"
        elif es_fecha_pasada(fecha):
            mensaje = "No puedes reservar una cancha en una fecha pasada."
            tipo_mensaje = "error"
        elif hora not in [h.lower() for h in HORARIOS]:
            mensaje = "La hora seleccionada no es válida."
            tipo_mensaje = "error"
        elif hora_ya_paso_para_hoy(fecha, hora):
            mensaje = "Esa hora ya pasó para hoy."
            tipo_mensaje = "error"
        elif horario_ocupado(fecha, cancha_id, hora):
            mensaje = "Esa hora ya está ocupada (por reserva o por reto)."
            tipo_mensaje = "error"
        else:
            reservas = leer_reservas()
            cancha_info = next((c for c in CANCHAS if c["id"] == int(cancha_id)), None)
            if not cancha_info:
                mensaje = "La cancha seleccionada no es válida."
                tipo_mensaje = "error"
            else:
                monto = obtener_precio_por_hora(hora)
                nueva = {
                    "id": (max([int(r.get("id", 0)) for r in reservas], default=0) + 1),
                    "nombre": nombre,
                    "telefono": telefono,
                    "fecha": fecha,
                    "cancha_id": int(cancha_id),
                    "cancha_nombre": cancha_info["nombre"],
                    "cancha_tipo": cancha_info["tipo"],
                    "hora": hora,
                    "monto": monto,
                    "metodo_pago": metodo_pago,
                    "pagado": False,
                    "sinpe_reportado_cliente": False,
                    "estado": "Reservada",
                    "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "origen": "Reserva"
                }
                reservas.append(nueva)
                guardar_reservas(reservas)
                registrar_evento("reserva", nueva)

                mensaje = f"Reserva confirmada. {cancha_info['nombre']} el {formatear_fecha_latina(fecha)} a las {hora}. Monto: {colones_filter(monto)}"
                tipo_mensaje = "success"
                reserva_creada = nueva

                # WhatsApp al cliente
                msg_wa = (
                    "✅ Reserva confirmada\n"
                    f"Cancha Suelo Tico: {cancha_info['nombre']} ({cancha_info['tipo']})\n"
                    f"Fecha: {fecha_larga_filter(fecha)}\n"
                    f"Hora: {hora}\n"
                    f"Monto: {colones_filter(monto)}\n\n"
                    "Si cancelas avisa con tiempo. Solo vuelve a ingresar al link y le das click al botón de cancelar.\n\n"
                    "Gracias por elegirnos."
                )
                whatsapp_link = wa_link(telefono, msg_wa)

                # WhatsApp al dueño (texto)
                texto_confirm = (
                    "✅ Reserva confirmada\n"
                    f"Cancha: {nueva.get('cancha_nombre')} ({nueva.get('cancha_tipo')})\n"
                    f"Fecha: {fecha_larga_filter(nueva.get('fecha'))}\n"
                    f"Hora: {nueva.get('hora')}\n"
                    f"Monto: {colones_filter(nueva.get('monto'))}\n\n"
                    "Si cancelas avisa con tiempo. Solo vuelve a ingresar al link y le das click al botón de cancelar.\n\n"
                    "Gracias por elegirnos."
                )
                wa_confirm_link = f"https://wa.me/{DUENO_TELEFONO}?text={quote_plus(texto_confirm)}"

                horas_disponibles = obtener_horas_disponibles(fecha, cancha_id)

    return render_template(
        "index.html",
        canchas=CANCHAS,
        horarios_disponibles=horas_disponibles,
        fecha_hoy=fecha_hoy_iso(),
        mensaje=mensaje,
        tipo_mensaje=tipo_mensaje,
        reserva_creada=reserva_creada,
        dueno_nombre=DUENO_NOMBRE,
        dueno_telefono=DUENO_TELEFONO,
        numero_sinpe=NUMERO_SINPE,
        fecha_sel=fecha_sel,
        cancha_sel=cancha_sel,
        whatsapp_link=whatsapp_link if reserva_creada else "",
        wa_confirm_link=wa_confirm_link if reserva_creada else "",
        wa_confirm_text=texto_confirm if reserva_creada else ""
    )

@app.route("/horarios_disponibles")
def horarios_disponibles_api():
    fecha = request.args.get("fecha", "").strip()
    cancha_id = request.args.get("cancha_id", "").strip()

    if not fecha or not cancha_id:
        return jsonify({"ok": True, "horarios": HORARIOS, "mensaje": "Selecciona fecha y cancha"})

    if es_fecha_pasada(fecha):
        return jsonify({"ok": False, "horarios": [], "mensaje": "No se permiten fechas pasadas"})

    try:
        disponibles = obtener_horas_disponibles(fecha, cancha_id)
        return jsonify({"ok": True, "horarios": disponibles, "mensaje": ""})
    except Exception:
        return jsonify({"ok": False, "horarios": [], "mensaje": "No se pudieron cargar los horarios"}), 400

@app.route("/horarios_disponibles_reto")
def horarios_disponibles_reto_api():
    fecha = request.args.get("fecha", "").strip()
    cancha_id = request.args.get("cancha_id", "").strip()

    if not fecha or not cancha_id:
        return jsonify({"ok": True, "horarios": HORARIOS, "mensaje": "Selecciona fecha y cancha"})

    if es_fecha_pasada(fecha):
        return jsonify({"ok": False, "horarios": [], "mensaje": "No se permiten fechas pasadas"})

    try:
        disponibles = obtener_horas_disponibles(fecha, cancha_id)
        return jsonify({"ok": True, "horarios": disponibles, "mensaje": ""})
    except Exception:
        return jsonify({"ok": False, "horarios": [], "mensaje": "No se pudieron cargar los horarios"}), 400

# ==========================
# CLIENTE: RETOS
# ==========================
@app.route("/retos")
def retos_publicos():
    autocerrar_retos()
    aviso = request.args.get("aviso", "").strip()
    retos = [r for r in leer_retos() if r.get("estado") == "Activo"]
    retos = sorted(retos, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))
    return render_template(
        "retos.html",
        retos=retos,
        canchas=CANCHAS,
        aviso=aviso,
        dueno_nombre=DUENO_NOMBRE,
        dueno_telefono=DUENO_TELEFONO
    )

@app.route("/retos/solicitar/<int:reto_id>", methods=["POST"])
def solicitar_reto_publicado(reto_id):
    autocerrar_retos()

    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    nota = request.form.get("nota", "").strip()
    metodo_pago = request.form.get("metodo_pago", "").strip() or "Efectivo"

    if not nombre or not telefono:
        return redirect(url_for("retos_publicos", aviso="Completa nombre y teléfono."))

    retos = leer_retos()
    reto = next((r for r in retos if int(r.get("id", 0)) == reto_id), None)
    if not reto or reto.get("estado") != "Activo":
        return redirect(url_for("retos_publicos", aviso="Ese reto no está activo."))

    solicitudes = leer_solicitudes_retos()
    tel_norm = normalizar_tel(telefono)

    for s in solicitudes:
        if s.get("tipo") == "Publicado" and int(s.get("reto_id", 0)) == reto_id:
            if normalizar_tel(s.get("telefono", "")) == tel_norm and s.get("estado") in {"Pendiente", "Aceptada"}:
                return redirect(url_for("retos_publicos", aviso="Ya enviaste solicitud para este reto."))

    nueva = {
        "id": siguiente_id(solicitudes),
        "tipo": "Publicado",
        "reto_id": reto_id,
        "nombre": nombre,
        "telefono": telefono,
        "nota": nota,
        "metodo_pago": metodo_pago,
        "estado": "Pendiente",
        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    solicitudes.append(nueva)
    guardar_solicitudes_retos(solicitudes)

    return redirect(url_for("retos_publicos", aviso="✅ Solicitud enviada. El dueño la revisará."))

@app.route("/retos/personalizado", methods=["POST"])
def solicitar_reto_personalizado():
    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip().lower()
    cancha_id = request.form.get("cancha_id", "").strip()
    metodo_pago = request.form.get("metodo_pago", "").strip() or "Efectivo"
    nota = request.form.get("nota", "").strip()

    if not nombre or not telefono or not fecha or not hora or not cancha_id:
        return redirect(url_for("retos_publicos", aviso="Completa nombre, teléfono, fecha, hora y cancha."))

    if es_fecha_pasada(fecha) or hora not in [h.lower() for h in HORARIOS] or hora_ya_paso_para_hoy(fecha, hora):
        return redirect(url_for("retos_publicos", aviso="La fecha/hora no es válida (pasada)."))

    if horario_ocupado(fecha, cancha_id, hora):
        return redirect(url_for("retos_publicos", aviso="Ese horario ya está ocupado (por reserva o reto). Elige otro."))

    solicitudes = leer_solicitudes_retos()
    tel_norm = normalizar_tel(telefono)

    for s in solicitudes:
        if s.get("tipo") == "Personalizado":
            if (
                normalizar_tel(s.get("telefono", "")) == tel_norm
                and s.get("estado") in {"Pendiente", "Aceptada"}
                and s.get("fecha") == fecha
                and str(s.get("hora", "")).lower() == hora
                and str(s.get("cancha_id", "")) == str(cancha_id)
            ):
                return redirect(url_for("retos_publicos", aviso="Ya pediste un reto similar. Espera respuesta del dueño."))

    nueva = {
        "id": siguiente_id(solicitudes),
        "tipo": "Personalizado",
        "reto_id": None,
        "fecha": fecha,
        "hora": hora,
        "cancha_id": int(cancha_id),
        "nombre": nombre,
        "telefono": telefono,
        "metodo_pago": metodo_pago,
        "nota": nota,
        "estado": "Pendiente",
        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    solicitudes.append(nueva)
    guardar_solicitudes_retos(solicitudes)

    return redirect(url_for("retos_publicos", aviso="✅ Solicitud de reto enviada. El dueño la revisará."))

# ==========================
# LOGIN ADMIN
# ==========================
@app.route("/login_admin", methods=["GET", "POST"])
def login_admin():
    if session.get("admin_logueado"):
        return redirect(url_for("admin"))

    mensaje = ""
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "").strip()

        if usuario == ADMIN_USUARIO and password == ADMIN_PASSWORD:
            session["admin_logueado"] = True
            session["admin_usuario"] = usuario
            return redirect(url_for("admin"))
        else:
            mensaje = "Usuario o contraseña incorrectos."

    return render_template("login.html", mensaje=mensaje)

@app.route("/logout_admin")
def logout_admin():
    session.clear()
    return redirect(url_for("login_admin"))

# ==========================
# ADMIN: OPERACIÓN
# ==========================
@app.route("/admin")
def admin():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    hoy = date.today()
    hoy_iso = hoy.isoformat()
    aviso = request.args.get("aviso", "").strip()

    reservas_dia = [r for r in reservas if r.get("fecha") == hoy_iso]
    reservas_dia_activas = [r for r in reservas_dia if r.get("estado") == "Reservada"]
    canceladas_dia = [r for r in reservas_dia if r.get("estado") == "Cancelada"]

    reservas_dia_activas = sorted(
        reservas_dia_activas,
        key=lambda r: hora_a_orden(r.get("hora", ""))
    )
    canceladas_dia = sorted(
        canceladas_dia,
        key=lambda r: hora_a_orden(r.get("hora", ""))
    )

    reservas_dia_pagadas = [r for r in reservas_dia_activas if r.get("pagado") is True]
    dinero_dia = sum(int(r.get("monto", 0)) for r in reservas_dia_pagadas)
    pagos_confirmados_dia = len(reservas_dia_pagadas)

    def bloque_horario(hora_txt):
        h = hora_a_orden(hora_txt)
        if h < 12:
            return "mañana"
        elif h < 18:
            return "tarde"
        return "noche"

    reservas_manana = [r for r in reservas_dia_activas if bloque_horario(r.get("hora", "")) == "mañana"]
    reservas_tarde = [r for r in reservas_dia_activas if bloque_horario(r.get("hora", "")) == "tarde"]
    reservas_noche = [r for r in reservas_dia_activas if bloque_horario(r.get("hora", "")) == "noche"]

    return render_template(
        "admin.html",
        admin_usuario=session.get("admin_usuario", "admin"),
        aviso=aviso,
        hoy_real_iso=hoy_iso,
        reservas_dia_activas=reservas_dia_activas,
        canceladas_dia=canceladas_dia,
        reservas_manana=reservas_manana,
        reservas_tarde=reservas_tarde,
        reservas_noche=reservas_noche,
        resumen_hoy={
            "dinero": dinero_dia,
            "reservadas": len(reservas_dia_activas),
            "canceladas": len(canceladas_dia),
            "pagos_confirmados": pagos_confirmados_dia,
            "fecha": hoy_iso
        }
    )
    # ==========================
    # BLOQUE RETOS
    # ==========================
    retos = leer_retos()
    solicitudes = leer_solicitudes_retos()

    retos = sorted(
        retos,
        key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", "")))
    )

    solicitudes_publicadas = [s for s in solicitudes if s.get("tipo") == "Publicado"]
    solicitudes_personalizadas = [s for s in solicitudes if s.get("tipo") == "Personalizado"]

    solicitudes_por_reto = {}
    for s in solicitudes_publicadas:
        rid = int(s.get("reto_id", 0))
        solicitudes_por_reto.setdefault(rid, []).append(s)

    for rid, lista in solicitudes_por_reto.items():
        lista.sort(
            key=lambda x: (
                0 if x.get("estado") == "Pendiente" else 1,
                x.get("fecha_creacion", "")
            )
        )

    solicitudes_personalizadas.sort(
        key=lambda s: (
            s.get("fecha", ""),
            hora_a_orden(s.get("hora", "")),
            s.get("fecha_creacion", "")
        )
    )

    return render_template(
        "admin.html",
        admin_usuario=session.get("admin_usuario", "admin"),
        aviso=aviso,
        fecha_resumen=dia_consulta_iso,
        hoy_real_iso=hoy_iso,

        # operación
        reservas_dia_activas=reservas_dia_activas,
        canceladas_dia=canceladas_dia,
        resumen_hoy=resumen_hoy,

        # retos
        retos=retos,
        solicitudes_por_reto=solicitudes_por_reto,
        solicitudes_personalizadas=solicitudes_personalizadas,

        # extras
        canchas=CANCHAS
    )
# ==========================
# ADMIN: AGENDA
# ==========================
@app.route("/admin_agenda")
def admin_agenda():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    hoy = date.today()
    hoy_iso = hoy.isoformat()

    fecha_filtro = request.args.get("fecha", "").strip()
    cancha_filtro = request.args.get("cancha_id", "").strip()
    busqueda = request.args.get("q", "").strip()

    reservas_filtradas = _filtrar_reservas(reservas, fecha_filtro, cancha_filtro, busqueda)
    reservas_vista_general = sorted(reservas_filtradas, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    pendientes_gestion = [r for r in reservas_filtradas if r.get("estado") != "Cancelada" and not r.get("pagado", False)]
    pendientes_gestion = sorted(pendientes_gestion, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    futuras = []
    for r in reservas:
        f = parse_fecha_segura(r.get("fecha", ""))
        if not f:
            continue
        if f > hoy and r.get("estado") == "Reservada":
            futuras.append(r)

    futuras = _filtrar_reservas(futuras, fecha_filtro, cancha_filtro, busqueda)
    futuras = sorted(futuras, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    futuras_por_fecha = {}
    for r in futuras:
        futuras_por_fecha.setdefault(r.get("fecha"), []).append(r)

    pendientes_total = len(pendientes_gestion)
    pendientes_sinpe = sum(1 for r in pendientes_gestion if r.get("metodo_pago") == "SINPE")
    pendientes_efectivo = sum(1 for r in pendientes_gestion if r.get("metodo_pago") == "Efectivo")
    sinpe_reportado = sum(1 for r in pendientes_gestion if r.get("metodo_pago") == "SINPE" and r.get("sinpe_reportado_cliente") is True)
    futuras_total = sum(len(v) for v in futuras_por_fecha.values())
    resultados = len(reservas_vista_general)

    resumen_agenda = {
        "pendientes_total": pendientes_total,
        "pendientes_sinpe": pendientes_sinpe,
        "pendientes_efectivo": pendientes_efectivo,
        "sinpe_reportado": sinpe_reportado,
        "futuras_total": futuras_total,
        "resultados": resultados
    }

    aviso = request.args.get("aviso", "").strip()

    return render_template(
        "admin_agenda.html",
        reservas=reservas_filtradas,
        reservas_vista_general=reservas_vista_general,
        pendientes_gestion=pendientes_gestion,
        futuras_por_fecha=futuras_por_fecha,
        canchas=CANCHAS,
        fecha_filtro=fecha_filtro,
        cancha_filtro=cancha_filtro,
        busqueda=busqueda,
        aviso=aviso,
        hoy_real_iso=hoy_iso,
        admin_usuario=session.get("admin_usuario", "admin"),
        resumen_agenda=resumen_agenda
    )

# ==========================
# ADMIN: HISTORIAL
# ==========================
@app.route("/admin_historial")
def admin_historial():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    hoy = date.today()

    desde_filtro = request.args.get("desde", "").strip()
    hasta_filtro = request.args.get("hasta", "").strip()
    cancha_filtro = request.args.get("cancha_id", "").strip()

    reservas_filtradas = reservas[:]
    d_desde = parse_fecha_segura(desde_filtro) if desde_filtro else None
    d_hasta = parse_fecha_segura(hasta_filtro) if hasta_filtro else None

    if d_desde or d_hasta:
        tmp = []
        for r in reservas_filtradas:
            f = parse_fecha_segura(r.get("fecha", ""))
            if not f:
                continue
            if d_desde and f < d_desde:
                continue
            if d_hasta and f > d_hasta:
                continue
            tmp.append(r)
        reservas_filtradas = tmp

    if cancha_filtro:
        try:
            reservas_filtradas = [r for r in reservas_filtradas if int(r.get("cancha_id", 0)) == int(cancha_filtro)]
        except ValueError:
            pass

    reservas_filtradas = sorted(reservas_filtradas, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    reservas_mes = []
    for r in reservas:
        f = parse_fecha_segura(r.get("fecha", ""))
        if not f:
            continue
        if f.year == hoy.year and f.month == hoy.month and r.get("estado") == "Reservada":
            reservas_mes.append(r)

    dinero_mes = sum(int(r.get("monto", 0)) for r in reservas_mes if r.get("pagado") is True)
    resumen_mes_hist = {"mes": hoy.month, "anio": hoy.year, "dinero": dinero_mes, "reservas": len(reservas_mes)}

    pagos_confirmados = [r for r in reservas_filtradas if r.get("estado") == "Reservada" and r.get("pagado") is True]
    canceladas = [r for r in reservas_filtradas if r.get("estado") == "Cancelada"]

    aviso = request.args.get("aviso", "").strip()

    return render_template(
        "admin_historial.html",
        reservas=reservas_filtradas,
        pagos_confirmados=sorted(pagos_confirmados, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", "")))),
        canceladas=sorted(canceladas, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", "")))),
        canchas=CANCHAS,
        cancha_filtro=cancha_filtro,
        resumen_mes_hist=resumen_mes_hist,
        aviso=aviso,
        admin_usuario=session.get("admin_usuario", "admin"),
        desde_filtro=desde_filtro,
        hasta_filtro=hasta_filtro
    )

# ==========================
# EXPORT CSV
# ==========================
@app.route("/admin_historial_export.csv")
def exportar_historial_csv():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()

    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    cancha_id = request.args.get("cancha_id", "").strip()

    d_desde = parse_fecha_segura(desde) if desde else None
    d_hasta = parse_fecha_segura(hasta) if hasta else None

    filtradas = reservas[:]

    if d_desde or d_hasta:
        tmp = []
        for r in filtradas:
            f = parse_fecha_segura(r.get("fecha", ""))
            if not f:
                continue
            if d_desde and f < d_desde:
                continue
            if d_hasta and f > d_hasta:
                continue
            tmp.append(r)
        filtradas = tmp

    if cancha_id:
        try:
            filtradas = [r for r in filtradas if int(r.get("cancha_id", 0)) == int(cancha_id)]
        except ValueError:
            pass

    filtradas = sorted(filtradas, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Fecha", "Hora", "Cliente", "Telefono", "Cancha", "Tipo", "Metodo", "Monto", "Estado", "Pago", "Origen"])

    for r in filtradas:
        estado = r.get("estado", "")
        if estado == "Cancelada":
            pago = "-"
        elif r.get("pagado") is True:
            pago = "Pagado"
        elif r.get("metodo_pago") == "SINPE" and r.get("sinpe_reportado_cliente") is True:
            pago = "SINPE reportado"
        else:
            pago = "Pendiente"

        writer.writerow([
            r.get("id", ""),
            formatear_fecha_latina(r.get("fecha", "")),
            r.get("hora", ""),
            r.get("nombre", ""),
            r.get("telefono", ""),
            r.get("cancha_nombre", ""),
            r.get("cancha_tipo", ""),
            r.get("metodo_pago", ""),
            colones_filter(r.get("monto", 0)),
            estado,
            pago,
            r.get("origen", "Reserva")
        ])

    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    output.close()

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=historial.csv"}
    )

# ==========================
# ADMIN: RETOS
# ==========================
@app.route("/admin_retos")
def admin_retos():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    autocerrar_retos()
    aviso = request.args.get("aviso", "").strip()

    retos = leer_retos()
    solicitudes = leer_solicitudes_retos()

    retos = sorted(retos, key=lambda r: (r.get("fecha", ""), hora_a_orden(r.get("hora", ""))))

    solicitudes_publicadas = [s for s in solicitudes if s.get("tipo") == "Publicado"]
    solicitudes_personalizadas = [s for s in solicitudes if s.get("tipo") == "Personalizado"]

    solicitudes_por_reto = {}
    for s in solicitudes_publicadas:
        rid = int(s.get("reto_id", 0))
        solicitudes_por_reto.setdefault(rid, []).append(s)

    for rid, lista in solicitudes_por_reto.items():
        lista.sort(key=lambda x: (0 if x.get("estado") == "Pendiente" else 1, x.get("fecha_creacion", "")))

    solicitudes_personalizadas.sort(key=lambda s: (s.get("fecha", ""), hora_a_orden(s.get("hora", "")), s.get("fecha_creacion", "")))

    return render_template(
        "admin_retos.html",
        admin_usuario=session.get("admin_usuario", "admin"),
        aviso=aviso,
        retos=retos,
        solicitudes_por_reto=solicitudes_por_reto,
        solicitudes_personalizadas=solicitudes_personalizadas,
        canchas=CANCHAS
    )

@app.route("/admin_retos/crear", methods=["POST"])
def admin_crear_reto():
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip().lower()
    cancha_id = request.form.get("cancha_id", "").strip()
    precio = request.form.get("precio", "0").strip()
    cupo = request.form.get("cupo", "10").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not fecha or not hora or not cancha_id:
        return redirect(url_for("admin_retos", aviso="Completa fecha, hora y cancha."))

    if es_fecha_pasada(fecha) or hora_ya_paso_para_hoy(fecha, hora):
        return redirect(url_for("admin_retos", aviso="No se puede crear un reto en una fecha/hora pasada."))

    if horario_ocupado(fecha, cancha_id, hora):
        return redirect(url_for("admin_retos", aviso="Ese horario ya está ocupado (por reserva o reto). Elige otro."))

    try:
        precio_i = int(precio) if precio else 0
    except ValueError:
        precio_i = 0
    try:
        cupo_i = int(cupo) if cupo else 10
    except ValueError:
        cupo_i = 10

    cancha_info = next((c for c in CANCHAS if int(c["id"]) == int(cancha_id)), None)
    if not cancha_info:
        return redirect(url_for("admin_retos", aviso="Cancha inválida."))

    retos = leer_retos()
    nuevo = {
        "id": siguiente_id(retos),
        "fecha": fecha,
        "hora": hora,
        "cancha_id": int(cancha_id),
        "cancha_nombre": cancha_info["nombre"],
        "tipo": cancha_info["tipo"],
        "precio": precio_i,
        "cupo": cupo_i,
        "descripcion": descripcion,
        "estado": "Activo",
        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    retos.append(nuevo)
    guardar_retos(retos)

    return redirect(url_for("admin_retos", aviso="✅ Reto creado."))

@app.route("/admin_retos/cerrar/<int:reto_id>")
def admin_cerrar_reto(reto_id):
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    retos = leer_retos()
    aviso = "No se encontró el reto."
    for r in retos:
        if int(r.get("id", 0)) == reto_id:
            r["estado"] = "Cerrado"
            r["fecha_cierre"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            aviso = "✅ Reto cerrado."
            break
    guardar_retos(retos)
    return redirect(url_for("admin_retos", aviso=aviso))

@app.route("/admin_retos/solicitud/<int:sol_id>/<accion>")
def admin_accion_solicitud(sol_id, accion):
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    solicitudes = leer_solicitudes_retos()
    retos = leer_retos()

    sol = next((s for s in solicitudes if int(s.get("id", 0)) == sol_id), None)
    if not sol:
        return redirect(url_for("admin_retos", aviso="No se encontró la solicitud."))

    if accion not in {"aceptar", "rechazar"}:
        return redirect(url_for("admin_retos", aviso="Acción inválida."))

    if accion == "rechazar":
        sol["estado"] = "Rechazada"
        guardar_solicitudes_retos(solicitudes)
        return redirect(url_for("admin_retos", aviso="✅ Solicitud rechazada."))

    if sol.get("estado") != "Pendiente":
        return redirect(url_for("admin_retos", aviso="Esa solicitud ya fue procesada."))

    if sol.get("tipo") == "Publicado":
        reto_id = int(sol.get("reto_id", 0))
        reto = next((r for r in retos if int(r.get("id", 0)) == reto_id), None)
        if not reto or reto.get("estado") != "Activo":
            return redirect(url_for("admin_retos", aviso="El reto ya no está activo."))

        reserva, err = crear_reserva_desde_reto(
            fecha=reto.get("fecha"),
            hora=reto.get("hora"),
            cancha_id=reto.get("cancha_id"),
            nombre=f"{sol.get('nombre')} (Reto)",
            telefono=sol.get("telefono"),
            metodo_pago=sol.get("metodo_pago") or "Efectivo",
            monto=reto.get("precio", 0),
            nota=sol.get("nota", ""),
            origen="Reto",
            reto_id=reto_id
        )
        if not reserva:
            return redirect(url_for("admin_retos", aviso=f"No se pudo crear la reserva del reto: {err}"))

        sol["estado"] = "Aceptada"
        reto["estado"] = "Cerrado"
        reto["fecha_cierre"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for s in solicitudes:
            if s.get("tipo") == "Publicado" and int(s.get("reto_id", 0)) == reto_id and int(s.get("id", 0)) != sol_id:
                if s.get("estado") == "Pendiente":
                    s["estado"] = "Rechazada"

        guardar_solicitudes_retos(solicitudes)
        guardar_retos(retos)
        return redirect(url_for("admin_retos", aviso="✅ Solicitud aceptada y reto convertido en reserva (con pagos)."))

    # Personalizado
    fecha = sol.get("fecha")
    hora = sol.get("hora")
    cancha_id = sol.get("cancha_id")
    monto = obtener_precio_por_hora(hora)

    reserva, err = crear_reserva_desde_reto(
        fecha=fecha,
        hora=hora,
        cancha_id=cancha_id,
        nombre=f"{sol.get('nombre')} (Reto personalizado)",
        telefono=sol.get("telefono"),
        metodo_pago=sol.get("metodo_pago") or "Efectivo",
        monto=monto,
        nota=sol.get("nota", ""),
        origen="Reto"
    )
    if not reserva:
        return redirect(url_for("admin_retos", aviso=f"No se pudo crear la reserva del reto: {err}"))

    sol["estado"] = "Aceptada"
    sol["reserva_id"] = reserva.get("id")
    guardar_solicitudes_retos(solicitudes)
    return redirect(url_for("admin_retos", aviso="✅ Reto personalizado aceptado y creado como reserva (con pagos)."))

# ==========================
# ACCIONES ADMIN (PAGOS)
# ==========================
@app.route("/confirmar_pago/<int:reserva_id>")
def confirmar_pago_admin(reserva_id):
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    reserva_actualizada = None
    aviso = "No se encontró la reserva."

    for r in reservas:
        if int(r.get("id", 0)) == reserva_id:
            if r.get("estado") != "Reservada":
                aviso = "No se puede confirmar pago de una reserva cancelada."
            elif r.get("pagado") is True:
                aviso = "Ese pago ya estaba confirmado."
            else:
                if r.get("fecha") != date.today().isoformat():
                    aviso = "El pago solo se puede confirmar el mismo día de la reserva."
                else:
                    r["pagado"] = True
                    r["fecha_pago_confirmado"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    reserva_actualizada = r
                    aviso = "Pago confirmado correctamente."
            break

    guardar_reservas(reservas)

    if reserva_actualizada:
        registrar_evento("pago_confirmado", reserva_actualizada)

    volver_a = request.args.get("volver_a", "").strip()
    if volver_a == "admin_agenda":
        return redirect(url_for(
            "admin_agenda",
            aviso=aviso,
            fecha=request.args.get("fecha", "").strip(),
            cancha_id=request.args.get("cancha_id", "").strip(),
            q=request.args.get("q", "").strip()
        ))

    return redirect(url_for("admin", aviso=aviso))

@app.route("/marcar_sinpe_reportado/<int:reserva_id>")
def marcar_sinpe_reportado_admin(reserva_id):
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    aviso = "No se encontró la reserva."

    for r in reservas:
        if int(r.get("id", 0)) == reserva_id:
            if r.get("estado") == "Cancelada":
                aviso = "No se puede marcar SINPE reportado en una reserva cancelada."
            elif r.get("metodo_pago") != "SINPE":
                aviso = "Esta reserva no es por SINPE."
            else:
                r["sinpe_reportado_cliente"] = True
                r["fecha_sinpe_reportado"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                aviso = "SINPE reportado por cliente marcado correctamente."
            break

    guardar_reservas(reservas)

    return redirect(url_for(
        "admin_agenda",
        aviso=aviso,
        fecha=request.args.get("fecha", "").strip(),
        cancha_id=request.args.get("cancha_id", "").strip(),
        q=request.args.get("q", "").strip()
    ))

@app.route("/desmarcar_sinpe_reportado/<int:reserva_id>")
def desmarcar_sinpe_reportado_admin(reserva_id):
    if not admin_requerido():
        return redirect(url_for("login_admin"))

    reservas = leer_reservas()
    aviso = "No se encontró la reserva."

    for r in reservas:
        if int(r.get("id", 0)) == reserva_id:
            if r.get("metodo_pago") != "SINPE":
                aviso = "Esta reserva no es por SINPE."
            else:
                r["sinpe_reportado_cliente"] = False
                r["fecha_sinpe_reportado"] = None
                aviso = "SINPE reportado desmarcado correctamente."
            break

    guardar_reservas(reservas)

    return redirect(url_for(
        "admin_agenda",
        aviso=aviso,
        fecha=request.args.get("fecha", "").strip(),
        cancha_id=request.args.get("cancha_id", "").strip(),
        q=request.args.get("q", "").strip()
    ))

if __name__ == "__main__":
    advertencias_seguridad_inicio()
    debug_mode = parse_bool_env(os.getenv("FLASK_DEBUG"), default=True)
    import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))