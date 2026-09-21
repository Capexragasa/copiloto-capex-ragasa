from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from copilot import build_prompt
from risk import CATEGORIES, global_risk, progress, recommendation
from storage import build_storage

st.set_page_config(
    page_title="Copiloto CAPEX | Ragasa",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

def get_app_password() -> str | None:
    try:
        value = st.secrets["app_password"]
    except Exception:
        return None
    return str(value) if value else None

def check_password() -> None:
    """Bloquea la app hasta que se escriba la contraseña correcta."""
    expected = get_app_password()
    if not expected:
        st.markdown("## Copiloto CAPEX")
        st.error(
            "Esta app todavía no tiene una contraseña configurada "
            "(falta el secreto `app_password` en Streamlit Cloud). "
            "Nadie puede entrar hasta que se configure."
        )
        st.stop()
    if st.session_state.get("auth_ok"):
        return
    st.markdown("## Copiloto CAPEX")
    st.caption("Acceso restringido · Ragasa")
    with st.form("login_form"):
        pwd = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        if pwd == expected:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()

check_password()

st.markdown(
    """
    <style>
    .stApp { background: #f7f6f1; }
    [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e6e1d5; }
    .capex-title { font-size: 2rem; font-weight: 750; color: #153d2d; margin-bottom: 0; }
    .capex-sub { color: #6f6a5e; margin-top: .1rem; }
    .memory-ok { padding: .45rem .65rem; border-radius: .5rem; background: #e7f3eb; color: #236642; font-size: .82rem; }
    .memory-local { padding: .45rem .65rem; border-radius: .5rem; background: #f5ebd8; color: #8a5b12; font-size: .82rem; }
    .risk-alto { color: #a83024; font-weight: 700; }
    .risk-medio { color: #a76913; font-weight: 700; }
    .risk-bajo { color: #28734a; font-weight: 700; }
    div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e6e1d5; padding: 1rem; border-radius: .8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@st.cache_resource
def storage():
    return build_storage(st.secrets)

db = storage()

def all_projects() -> list[dict[str, Any]]:
    return db.list_projects()

def next_folio(projects: list[dict[str, Any]]) -> str:
    year = datetime.now().year
    prefix = f"CAPEX-{year}-"
    numbers = []
    for project in projects:
        folio = project.get("folio", "")
        if folio.startswith(prefix):
            try:
                numbers.append(int(folio.removeprefix(prefix)))
            except ValueError:
                pass
    return f"{prefix}{max(numbers, default=0) + 1:03d}"

def blank_project(folio: str, name: str, buyer: str, amount: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "folio": folio,
        "nombre": name,
        "comprador": buyer,
        "monto_estimado": amount,
        "estatus": "Activo",
        "fecha_creacion": timestamp[:10],
        "updated_at": timestamp,
        "pendientes": [],
        "history": [
            {
                "fecha": timestamp,
                "modulo": "Sistema",
                "accion": "Expediente creado",
                "detalle": name,
            }
        ],
        "ia_history": [],
        **{f"m{number}": {"estado": "pendiente"} for number in range(1, 7)},
    }

def add_history(project: dict[str, Any], module: str, action: str, detail: str = "") -> None:
    project.setdefault("history", []).append(
        {"fecha": now_iso(), "modulo": module, "accion": action, "detalle": detail}
    )

def save(project: dict[str, Any], module: str, action: str, detail: str = "") -> None:
    project["updated_at"] = now_iso()
    add_history(project, module, action, detail)
    db.save_project(project)
    st.session_state["selected_folio"] = project["folio"]
    st.toast("Cambios guardados", icon="✅")

def risk_html(level: str) -> str:
    css = {"Alto": "risk-alto", "Medio": "risk-medio", "Bajo": "risk-bajo"}.get(level, "")
    return f'<span class="{css}">{level}</span>'

def normalize_rows(rows: Any) -> list[dict[str, Any]]:
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    return [
        {key: ("" if value is None else value) for key, value in row.items()}
        for row in rows
        if any(str(value).strip() for value in row.values() if value is not None)
    ]

def ai_panel(project: dict[str, Any], module: str) -> None:
    with st.expander("🧠 Analizar con Copilot", expanded=False):
        st.caption(
            "El sistema prepara el expediente completo. Copia el texto en Copilot y pega aquí la respuesta; no utiliza API ni genera costos."
        )
        prompt = build_prompt(project, module)
        st.code(prompt, language=None, wrap_lines=True)
        st.download_button(
            "Descargar prompt",
            prompt,
            file_name=f"{project['folio']}_{module}_prompt.txt",
            mime="text/plain",
            key=f"prompt_{module}_{project['folio']}",
        )
        response = st.text_area(
            "Pega la respuesta de Copilot",
            key=f"ai_response_{module}_{project['folio']}",
            height=180,
        )
        if st.button("Guardar respuesta en la memoria", key=f"save_ai_{module}_{project['folio']}"):
            if not response.strip():
                st.warning("Primero pega la respuesta de Copilot.")
            else:
                record = {"fecha": now_iso(), "modulo": module, "respuesta": response.strip()}
                project.setdefault("ia_history", []).append(record)
                project[module.lower()]["ultima_respuesta_ia"] = response.strip()
                save(project, module, "Respuesta de Copilot guardada")
                st.rerun()

def render_dashboard(projects: list[dict[str, Any]]) -> None:
    st.markdown('<p class="capex-title">Copiloto CAPEX</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="capex-sub">Vista ejecutiva de solicitudes, riesgo y próximos pasos</p>',
        unsafe_allow_html=True,
    )
    active = [p for p in projects if p.get("estatus") != "Archivado"]
    archived = [p for p in projects if p.get("estatus") == "Archivado"]
    high = sum(global_risk(p) == "Alto" for p in active)
    medium = sum(global_risk(p) == "Medio" for p in active)
    cols = st.columns(4)
    cols[0].metric("Proyectos activos", len(active))
    cols[1].metric("Riesgo alto", high)
    cols[2].metric("Riesgo medio", medium)
    cols[3].metric("Archivados", len(archived))

    if not projects:
        st.info("Todavía no hay proyectos. Crea el primero desde el menú lateral.")
        return

    rows = []
    for project in projects:
        rows.append(
            {
                "Folio": project.get("folio"),
                "Proyecto": project.get("nombre"),
                "Responsable": project.get("comprador"),
                "Riesgo": global_risk(project),
                "Avance": f"{progress(project)}%",
                "Estatus": project.get("estatus", "Activo"),
                "Última actualización": project.get("updated_at", "")[:10],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

def render_m1(project: dict[str, Any]) -> None:
    data = project.get("m1", {})
    description = st.text_area("Descripción de la necesidad", data.get("descripcion", ""), key=f"m1_desc_{project['folio']}")
    c1, c2, c3 = st.columns(3)
    area = c1.text_input("Área / planta", data.get("area", ""), key=f"m1_area_{project['folio']}")
    deadline = c2.text_input("Plazo requerido", data.get("plazo", ""), key=f"m1_plazo_{project['folio']}")
    risk_request = c3.selectbox(
        "Riesgo de la solicitud",
        ["Pendiente", "Bajo", "Medio", "Alto"],
        index=["Pendiente", "Bajo", "Medio", "Alto"].index(data.get("riesgo_solicitud", {}).get("nivel", "Pendiente")),
        key=f"m1_risk_{project['folio']}",
    )
    technical = st.text_area("Información técnica disponible", data.get("info_tecnica", ""), key=f"m1_tech_{project['folio']}")
    risk_why = st.text_input(
        "Justificación del riesgo",
        data.get("riesgo_solicitud", {}).get("justificacion", ""),
        key=f"m1_why_{project['folio']}",
    )
    rows = [
        {
            "nombre": row.get("nombre", ""),
            "descripcion": row.get("descripcion", ""),
            "riesgo": row.get("riesgo", {}).get("nivel", row.get("riesgo", "Pendiente")),
            "justificacion": row.get("riesgo", {}).get("justificacion", row.get("justificacion", "")),
        }
        for row in data.get("alternativas", [])
    ] or [{"nombre": "", "descripcion": "", "riesgo": "Pendiente", "justificacion": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "nombre": "Alternativa",
            "descripcion": "Descripción",
            "riesgo": st.column_config.SelectboxColumn("Riesgo", options=["Pendiente", "Bajo", "Medio", "Alto"]),
            "justificacion": "Justificación",
        },
        key=f"m1_alts_{project['folio']}",
    )
    cleaned = normalize_rows(edited)
    names = [row["nombre"] for row in cleaned if str(row.get("nombre", "")).strip()]
    selected_current = data.get("alternativa_seleccionada", "")
    selected = st.selectbox(
        "Alternativa seleccionada",
        [""] + names,
        index=([""] + names).index(selected_current) if selected_current in names else 0,
        key=f"m1_selected_{project['folio']}",
    )
    if st.button("Guardar módulo 1", type="primary", key=f"m1_save_{project['folio']}"):
        if not description.strip() or risk_request == "Pendiente" or not selected:
            st.warning("Completa la descripción, el riesgo y selecciona una alternativa.")
        else:
            alternatives = [
                {
                    "nombre": str(row["nombre"]).strip(),
                    "descripcion": str(row.get("descripcion", "")).strip(),
                    "riesgo": {
                        "nivel": row.get("riesgo", "Pendiente"),
                        "justificacion": str(row.get("justificacion", "")).strip(),
                    },
                }
                for row in cleaned
                if str(row.get("nombre", "")).strip()
            ]
            project["m1"] = {
                "estado": "completo",
                "descripcion": description,
                "area": area,
                "plazo": deadline,
                "info_tecnica": technical,
                "riesgo_solicitud": {"nivel": risk_request, "justificacion": risk_why},
                "alternativas": alternatives,
                "alternativa_seleccionada": selected,
            }
            save(project, "M1", "Solicitud y alternativas actualizadas", selected)
            st.rerun()
    ai_panel(project, "M1")

def render_m2(project: dict[str, Any]) -> None:
    data = project.get("m2", {})
    st.caption(f"Alternativa seleccionada: {project.get('m1', {}).get('alternativa_seleccionada', 'Pendiente')}")
    c1, c2 = st.columns(2)
    specialty = c1.text_input("Producto / servicio / especialidad", data.get("especialidad", ""), key=f"m2_sp_{project['folio']}")
    location = c2.text_input("Ubicación", data.get("ubicacion", ""), key=f"m2_loc_{project['folio']}")
    requirements = st.text_area("Requisitos técnicos", data.get("requisitos", ""), key=f"m2_req_{project['folio']}")
    rows = [
        {
            "nombre": row.get("nombre", ""),
            "clasificacion": row.get("clasificacion", "Sin información suficiente"),
            "coincidencia": row.get("justificacion", ""),
            "riesgo": row.get("riesgo", {}).get("nivel", "Pendiente"),
            "justificacion_riesgo": row.get("riesgo", {}).get("justificacion", ""),
        }
        for row in data.get("proveedores", [])
    ] or [{"nombre": "", "clasificacion": "Sin información suficiente", "coincidencia": "", "riesgo": "Pendiente", "justificacion_riesgo": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "clasificacion": st.column_config.SelectboxColumn(
                "Clasificación",
                options=["Recomendado para invitar", "Requiere validación adicional", "No recomendado", "Sin información suficiente"],
            ),
            "riesgo": st.column_config.SelectboxColumn("Riesgo", options=["Pendiente", "Bajo", "Medio", "Alto"]),
        },
        key=f"m2_providers_{project['folio']}",
    )
    cleaned = normalize_rows(edited)
    names = [str(row["nombre"]).strip() for row in cleaned if str(row.get("nombre", "")).strip()]
    current = data.get("proveedor_recomendado", "")
    selected = st.selectbox(
        "Proveedor recomendado",
        [""] + names,
        index=([""] + names).index(current) if current in names else 0,
        key=f"m2_selected_{project['folio']}",
    )
    if st.button("Guardar módulo 2", type="primary", key=f"m2_save_{project['folio']}"):
        if not names or not selected:
            st.warning("Agrega al menos un proveedor y selecciona el recomendado.")
        else:
            providers = [
                {
                    "nombre": str(row["nombre"]).strip(),
                    "clasificacion": row.get("clasificacion", "Sin información suficiente"),
                    "justificacion": str(row.get("coincidencia", "")).strip(),
                    "riesgo": {
                        "nivel": row.get("riesgo", "Pendiente"),
                        "justificacion": str(row.get("justificacion_riesgo", "")).strip(),
                    },
                }
                for row in cleaned
                if str(row.get("nombre", "")).strip()
            ]
            project["m2"] = {
                "estado": "completo",
                "especialidad": specialty,
                "ubicacion": location,
                "requisitos": requirements,
                "proveedores": providers,
                "proveedor_recomendado": selected,
            }
            save(project, "M2", "Proveedores actualizados", selected)
            st.rerun()
    ai_panel(project, "M2")

def render_m3(project: dict[str, Any]) -> None:
    data = project.get("m3", {})
    statuses = ["No iniciado", "En proceso", "Precalificado", "Condicionado", "Rechazado"]
    c1, c2 = st.columns(2)
    status = c1.selectbox(
        "Estatus de precalificación",
        statuses,
        index=statuses.index(data.get("estatus", "No iniciado")) if data.get("estatus", "No iniciado") in statuses else 0,
        key=f"m3_status_{project['folio']}",
    )
    score = c2.number_input("Score", min_value=0, max_value=100, value=int(data.get("score", 0) or 0), key=f"m3_score_{project['folio']}")
    notes = st.text_area("Documentación faltante / observaciones", data.get("observaciones", ""), key=f"m3_notes_{project['folio']}")
    if st.button("Guardar módulo 3", type="primary", key=f"m3_save_{project['folio']}"):
        project["m3"] = {"estado": "completo", "estatus": status, "score": score, "observaciones": notes}
        save(project, "M3", "Precalificación actualizada", status)
        st.rerun()
    ai_panel(project, "M3")

def render_m4(project: dict[str, Any]) -> None:
    data = project.get("m4", {})
    rows = [
        {
            "categoria": label,
            "nivel": data.get("categorias", {}).get(key, {}).get("nivel", "Pendiente"),
            "justificacion": data.get("categorias", {}).get(key, {}).get("justificacion", ""),
        }
        for key, label in CATEGORIES
    ]
    edited = st.data_editor(
        rows,
        use_container_width=True,
        disabled=["categoria"],
        column_config={"nivel": st.column_config.SelectboxColumn("Nivel", options=["Pendiente", "Bajo", "Medio", "Alto"])},
        key=f"m4_categories_{project['folio']}",
    )
    impact = st.text_area("Impacto potencial", data.get("impacto_potencial", ""), key=f"m4_impact_{project['folio']}")
    actions = st.text_area(
        "Acciones preventivas (una por línea)",
        "\n".join(data.get("acciones_preventivas", [])),
        key=f"m4_actions_{project['folio']}",
    )
    alerts = st.text_area("Alertas (una por línea)", "\n".join(data.get("alertas", [])), key=f"m4_alerts_{project['folio']}")
    if st.button("Guardar módulo 4", type="primary", key=f"m4_save_{project['folio']}"):
        edited_rows = normalize_rows(edited)
        if any(row.get("nivel") == "Pendiente" for row in edited_rows):
            st.warning("Asigna un nivel a las siete categorías.")
        else:
            categories = {
                key: {
                    "nivel": edited_rows[index]["nivel"],
                    "justificacion": str(edited_rows[index].get("justificacion", "")).strip(),
                }
                for index, (key, _) in enumerate(CATEGORIES)
            }
            project["m4"] = {
                "estado": "completo",
                "categorias": categories,
                "impacto_potencial": impact,
                "acciones_preventivas": [line.strip() for line in actions.splitlines() if line.strip()],
                "alertas": [line.strip() for line in alerts.splitlines() if line.strip()],
            }
            level = global_risk(project)
            project["m4"]["riesgo_global"] = level
            project["m4"]["recomendacion_final"] = recommendation(level)
            save(project, "M4", "Riesgo consolidado actualizado", level)
            st.rerun()
    current = global_risk(project)
    st.markdown(f"**Riesgo global actual:** {risk_html(current)}", unsafe_allow_html=True)
    st.write(f"**Recomendación:** {recommendation(current)}")
    ai_panel(project, "M4")

def render_m5(project: dict[str, Any]) -> None:
    data = project.get("m5", {})
    c1, c2 = st.columns(2)
    reference = c1.text_input("Precio o índice de referencia", data.get("precio_referencia", ""), key=f"m5_price_{project['folio']}")
    date = c2.date_input("Fecha de consulta", key=f"m5_date_{project['folio']}")
    source = st.text_input("Fuente o vínculo", data.get("fuente", ""), key=f"m5_source_{project['folio']}")
    drivers = st.text_area("Commodities y drivers identificados", data.get("drivers", ""), key=f"m5_drivers_{project['folio']}")
    forecast = st.text_area("Tendencia / forecast de 12 meses", data.get("forecast", ""), key=f"m5_forecast_{project['folio']}")
    if st.button("Guardar módulo 5", type="primary", key=f"m5_save_{project['folio']}"):
        project["m5"] = {
            "estado": "completo",
            "precio_referencia": reference,
            "fecha_consulta": date.isoformat(),
            "fuente": source,
            "drivers": drivers,
            "forecast": forecast,
        }
        save(project, "M5", "Análisis de mercado actualizado", reference)
        st.rerun()
    ai_panel(project, "M5")

def render_m6(project: dict[str, Any]) -> None:
    data = project.get("m6", {})
    rows = data.get("cotizaciones", []) or [
        {"proveedor": project.get("m2", {}).get("proveedor_recomendado", ""), "monto": "", "moneda": "MXN", "plazo": "", "condiciones": ""}
    ]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={"moneda": st.column_config.SelectboxColumn("Moneda", options=["MXN", "USD", "EUR", "Otra"])},
        key=f"m6_quotes_{project['folio']}",
    )
    comparison = st.text_area("Comparación de cotizaciones", data.get("comparacion", ""), key=f"m6_compare_{project['folio']}")
    final = st.text_area("Recomendación integral final", data.get("recomendacion_integral", ""), key=f"m6_final_{project['folio']}")
    next_action = st.text_input("Próxima acción", data.get("proxima_accion", ""), key=f"m6_next_{project['folio']}")
    if st.button("Guardar módulo 6", type="primary", key=f"m6_save_{project['folio']}"):
        if not final.strip():
            st.warning("Escribe la recomendación integral final.")
        else:
            project["m6"] = {
                "estado": "completo",
                "cotizaciones": normalize_rows(edited),
                "comparacion": comparison,
                "recomendacion_integral": final,
                "proxima_accion": next_action,
            }
            project["pendientes"] = [next_action] if next_action.strip() else []
            save(project, "M6", "Cotizaciones y recomendación actualizadas", next_action)
            st.rerun()
    ai_panel(project, "M6")

def render_project(project: dict[str, Any]) -> None:
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown(f'<p class="capex-title">{project["nombre"]}</p>', unsafe_allow_html=True)
        st.caption(f"{project['folio']} · Responsable: {project.get('comprador') or 'Sin asignar'}")
    with c2:
        st.metric("Avance", f"{progress(project)}%")
    st.progress(progress(project) / 100)
    st.markdown(
        f"**Riesgo:** {risk_html(global_risk(project))} &nbsp;&nbsp; **Estatus:** {project.get('estatus', 'Activo')}",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["1. Solicitud", "2. Proveedores", "3. Precalificación", "4. Riesgos", "5. Mercado", "6. Cotizaciones", "Memoria", "Archivo"])
    with tabs[0]:
        render_m1(project)
    with tabs[1]:
        render_m2(project)
    with tabs[2]:
        render_m3(project)
    with tabs[3]:
        render_m4(project)
    with tabs[4]:
        render_m5(project)
    with tabs[5]:
        render_m6(project)
    with tabs[6]:
        st.subheader("Memoria del proyecto")
        if project.get("ia_history"):
            st.write("**Respuestas de IA guardadas**")
            for item in reversed(project["ia_history"]):
                with st.expander(f"{item['modulo']} · {item['fecha'][:16].replace('T', ' ')}"):
                    st.write(item["respuesta"])
        st.write("**Historial de cambios**")
        st.dataframe(project.get("history", []), use_container_width=True, hide_index=True)
    with tabs[7]:
        archive_project(project)

def archive_project(project: dict[str, Any]) -> None:
    st.subheader("Respaldo y archivo")
    payload = json.dumps(project, ensure_ascii=False, indent=2)
    st.download_button(
        "Descargar expediente completo (.json)",
        payload,
        file_name=f"{project['folio']}_expediente.json",
        mime="application/json",
        key=f"download_archive_{project['folio']}",
    )
    if project.get("estatus") != "Archivado":
        st.caption("Descarga el respaldo y guárdalo en la carpeta corporativa antes de archivar.")
        confirm = st.checkbox("Confirmo que descargué el respaldo", key=f"archive_confirm_{project['folio']}")
        if st.button("Marcar como archivado", disabled=not confirm, key=f"archive_{project['folio']}"):
            project["estatus"] = "Archivado"
            project["fecha_archivo"] = now_iso()
            save(project, "Archivo", "Proyecto archivado")
            st.rerun()
    else:
        st.success("Este proyecto está archivado. El expediente completo sigue disponible.")
        if st.button("Reactivar proyecto", key=f"reactivate_{project['folio']}"):
            project["estatus"] = "Activo"
            save(project, "Archivo", "Proyecto reactivado")
            st.rerun()
        st.warning("La depuración de detalle se habilitará después de validar el flujo de respaldo para evitar pérdidas accidentales.")

def new_project_dialog(projects: list[dict[str, Any]]) -> None:
    st.subheader("Nueva solicitud CAPEX")
    with st.form("new_project", clear_on_submit=True):
        proposed = next_folio(projects)
        folio = st.text_input("Folio", proposed)
        name = st.text_input("Nombre del proyecto")
        buyer = st.text_input("Responsable")
        amount = st.text_input("Monto estimado")
        submitted = st.form_submit_button("Crear expediente", type="primary")
    if submitted:
        if not folio.strip() or not name.strip():
            st.warning("El folio y el nombre son obligatorios.")
        elif db.get_project(folio.strip()):
            st.error("Ese folio ya existe.")
        else:
            project = blank_project(folio.strip(), name.strip(), buyer.strip(), amount.strip())
            db.save_project(project)
            st.session_state["selected_folio"] = project["folio"]
            st.session_state["page"] = "Proyecto"
            st.rerun()

def import_project() -> None:
    st.subheader("Restaurar expediente")
    uploaded = st.file_uploader("Selecciona un respaldo .json", type=["json"])
    if uploaded and st.button("Restaurar", type="primary"):
        try:
            project = json.loads(uploaded.getvalue().decode("utf-8"))
            if not isinstance(project, dict) or not project.get("folio") or not project.get("nombre"):
                raise ValueError("Estructura incompleta")
            project["updated_at"] = now_iso()
            add_history(project, "Archivo", "Expediente restaurado")
            db.save_project(project)
            st.session_state["selected_folio"] = project["folio"]
            st.session_state["page"] = "Proyecto"
            st.success("Expediente restaurado correctamente.")
            st.rerun()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            st.error(f"El archivo no es un respaldo válido: {exc}")

projects = all_projects()
with st.sidebar:
    st.markdown("## Copiloto CAPEX")
    if db.mode == "firestore":
        st.markdown('<div class="memory-ok">● Memoria compartida activa</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="memory-local">● Memoria local de prueba</div>', unsafe_allow_html=True)
        st.caption("Cuando configuremos Firestore, tú y tu jefe verán la misma información.")

    page = st.radio(
        "Navegación",
        ["Dashboard", "Proyecto", "Nueva solicitud", "Restaurar respaldo"],
        index=["Dashboard", "Proyecto", "Nueva solicitud", "Restaurar respaldo"].index(st.session_state.get("page", "Dashboard")),
    )
    st.session_state["page"] = page

    project_labels = {
        f"{p['folio']} · {p['nombre']}": p["folio"]
        for p in projects
        if p.get("estatus") != "Archivado"
    }
    if project_labels:
        labels = list(project_labels)
        current_folio = st.session_state.get("selected_folio")
        current_label = next((label for label, folio in project_labels.items() if folio == current_folio), labels[0])
        selected_label = st.selectbox("Abrir proyecto", labels, index=labels.index(current_label))
        st.session_state["selected_folio"] = project_labels[selected_label]
        if st.button("Abrir expediente", use_container_width=True):
            st.session_state["page"] = "Proyecto"
            st.rerun()

    st.divider()
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state["auth_ok"] = False
        st.rerun()

if page == "Dashboard":
    render_dashboard(projects)
elif page == "Nueva solicitud":
    new_project_dialog(projects)
elif page == "Restaurar respaldo":
    import_project()
else:
    folio = st.session_state.get("selected_folio")
    project = db.get_project(folio) if folio else None
    if project:
        render_project(project)
    else:
        st.info("Selecciona o crea un proyecto.")

from copilot import build_prompt
from risk import CATEGORIES, global_risk, progress, recommendation
from storage import build_storage


st.set_page_config(
    page_title="Copiloto CAPEX | Ragasa",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #f7f6f1; }
    [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e6e1d5; }
    .capex-title { font-size: 2rem; font-weight: 750; color: #153d2d; margin-bottom: 0; }
    .capex-sub { color: #6f6a5e; margin-top: .1rem; }
    .memory-ok { padding: .45rem .65rem; border-radius: .5rem; background: #e7f3eb; color: #236642; font-size: .82rem; }
    .memory-local { padding: .45rem .65rem; border-radius: .5rem; background: #f5ebd8; color: #8a5b12; font-size: .82rem; }
    .risk-alto { color: #a83024; font-weight: 700; }
    .risk-medio { color: #a76913; font-weight: 700; }
    .risk-bajo { color: #28734a; font-weight: 700; }
    div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e6e1d5; padding: 1rem; border-radius: .8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@st.cache_resource
def storage():
    return build_storage(st.secrets)


db = storage()


def all_projects() -> list[dict[str, Any]]:
    return db.list_projects()


def next_folio(projects: list[dict[str, Any]]) -> str:
    year = datetime.now().year
    prefix = f"CAPEX-{year}-"
    numbers = []
    for project in projects:
        folio = project.get("folio", "")
        if folio.startswith(prefix):
            try:
                numbers.append(int(folio.removeprefix(prefix)))
            except ValueError:
                pass
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def blank_project(folio: str, name: str, buyer: str, amount: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "folio": folio,
        "nombre": name,
        "comprador": buyer,
        "monto_estimado": amount,
        "estatus": "Activo",
        "fecha_creacion": timestamp[:10],
        "updated_at": timestamp,
        "pendientes": [],
        "history": [
            {
                "fecha": timestamp,
                "modulo": "Sistema",
                "accion": "Expediente creado",
                "detalle": name,
            }
        ],
        "ia_history": [],
        **{f"m{number}": {"estado": "pendiente"} for number in range(1, 7)},
    }


def add_history(project: dict[str, Any], module: str, action: str, detail: str = "") -> None:
    project.setdefault("history", []).append(
        {"fecha": now_iso(), "modulo": module, "accion": action, "detalle": detail}
    )


def save(project: dict[str, Any], module: str, action: str, detail: str = "") -> None:
    project["updated_at"] = now_iso()
    add_history(project, module, action, detail)
    db.save_project(project)
    st.session_state["selected_folio"] = project["folio"]
    st.toast("Cambios guardados", icon="✅")


def risk_html(level: str) -> str:
    css = {"Alto": "risk-alto", "Medio": "risk-medio", "Bajo": "risk-bajo"}.get(level, "")
    return f'<span class="{css}">{level}</span>'


def normalize_rows(rows: Any) -> list[dict[str, Any]]:
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict("records")
    return [
        {key: ("" if value is None else value) for key, value in row.items()}
        for row in rows
        if any(str(value).strip() for value in row.values() if value is not None)
    ]


def ai_panel(project: dict[str, Any], module: str) -> None:
    with st.expander("🧠 Analizar con Copilot", expanded=False):
        st.caption(
            "El sistema prepara el expediente completo. Copia el texto en Copilot y pega aquí la respuesta; no utiliza API ni genera costos."
        )
        prompt = build_prompt(project, module)
        st.code(prompt, language=None, wrap_lines=True)
        st.download_button(
            "Descargar prompt",
            prompt,
            file_name=f"{project['folio']}_{module}_prompt.txt",
            mime="text/plain",
            key=f"prompt_{module}_{project['folio']}",
        )
        response = st.text_area(
            "Pega la respuesta de Copilot",
            key=f"ai_response_{module}_{project['folio']}",
            height=180,
        )
        if st.button("Guardar respuesta en la memoria", key=f"save_ai_{module}_{project['folio']}"):
            if not response.strip():
                st.warning("Primero pega la respuesta de Copilot.")
            else:
                record = {"fecha": now_iso(), "modulo": module, "respuesta": response.strip()}
                project.setdefault("ia_history", []).append(record)
                project[module.lower()]["ultima_respuesta_ia"] = response.strip()
                save(project, module, "Respuesta de Copilot guardada")
                st.rerun()


def render_dashboard(projects: list[dict[str, Any]]) -> None:
    st.markdown('<p class="capex-title">Copiloto CAPEX</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="capex-sub">Vista ejecutiva de solicitudes, riesgo y próximos pasos</p>',
        unsafe_allow_html=True,
    )
    active = [p for p in projects if p.get("estatus") != "Archivado"]
    archived = [p for p in projects if p.get("estatus") == "Archivado"]
    high = sum(global_risk(p) == "Alto" for p in active)
    medium = sum(global_risk(p) == "Medio" for p in active)
    cols = st.columns(4)
    cols[0].metric("Proyectos activos", len(active))
    cols[1].metric("Riesgo alto", high)
    cols[2].metric("Riesgo medio", medium)
    cols[3].metric("Archivados", len(archived))

    if not projects:
        st.info("Todavía no hay proyectos. Crea el primero desde el menú lateral.")
        return

    rows = []
    for project in projects:
        rows.append(
            {
                "Folio": project.get("folio"),
                "Proyecto": project.get("nombre"),
                "Responsable": project.get("comprador"),
                "Riesgo": global_risk(project),
                "Avance": f"{progress(project)}%",
                "Estatus": project.get("estatus", "Activo"),
                "Última actualización": project.get("updated_at", "")[:10],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_m1(project: dict[str, Any]) -> None:
    data = project.get("m1", {})
    description = st.text_area("Descripción de la necesidad", data.get("descripcion", ""), key=f"m1_desc_{project['folio']}")
    c1, c2, c3 = st.columns(3)
    area = c1.text_input("Área / planta", data.get("area", ""), key=f"m1_area_{project['folio']}")
    deadline = c2.text_input("Plazo requerido", data.get("plazo", ""), key=f"m1_plazo_{project['folio']}")
    risk_request = c3.selectbox(
        "Riesgo de la solicitud",
        ["Pendiente", "Bajo", "Medio", "Alto"],
        index=["Pendiente", "Bajo", "Medio", "Alto"].index(data.get("riesgo_solicitud", {}).get("nivel", "Pendiente")),
        key=f"m1_risk_{project['folio']}",
    )
    technical = st.text_area("Información técnica disponible", data.get("info_tecnica", ""), key=f"m1_tech_{project['folio']}")
    risk_why = st.text_input(
        "Justificación del riesgo",
        data.get("riesgo_solicitud", {}).get("justificacion", ""),
        key=f"m1_why_{project['folio']}",
    )
    rows = [
        {
            "nombre": row.get("nombre", ""),
            "descripcion": row.get("descripcion", ""),
            "riesgo": row.get("riesgo", {}).get("nivel", row.get("riesgo", "Pendiente")),
            "justificacion": row.get("riesgo", {}).get("justificacion", row.get("justificacion", "")),
        }
        for row in data.get("alternativas", [])
    ] or [{"nombre": "", "descripcion": "", "riesgo": "Pendiente", "justificacion": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "nombre": "Alternativa",
            "descripcion": "Descripción",
            "riesgo": st.column_config.SelectboxColumn("Riesgo", options=["Pendiente", "Bajo", "Medio", "Alto"]),
            "justificacion": "Justificación",
        },
        key=f"m1_alts_{project['folio']}",
    )
    cleaned = normalize_rows(edited)
    names = [row["nombre"] for row in cleaned if str(row.get("nombre", "")).strip()]
    selected_current = data.get("alternativa_seleccionada", "")
    selected = st.selectbox(
        "Alternativa seleccionada",
        [""] + names,
        index=([""] + names).index(selected_current) if selected_current in names else 0,
        key=f"m1_selected_{project['folio']}",
    )
    if st.button("Guardar módulo 1", type="primary", key=f"m1_save_{project['folio']}"):
        if not description.strip() or risk_request == "Pendiente" or not selected:
            st.warning("Completa la descripción, el riesgo y selecciona una alternativa.")
        else:
            alternatives = [
                {
                    "nombre": str(row["nombre"]).strip(),
                    "descripcion": str(row.get("descripcion", "")).strip(),
                    "riesgo": {
                        "nivel": row.get("riesgo", "Pendiente"),
                        "justificacion": str(row.get("justificacion", "")).strip(),
                    },
                }
                for row in cleaned
                if str(row.get("nombre", "")).strip()
            ]
            project["m1"] = {
                "estado": "completo",
                "descripcion": description,
                "area": area,
                "plazo": deadline,
                "info_tecnica": technical,
                "riesgo_solicitud": {"nivel": risk_request, "justificacion": risk_why},
                "alternativas": alternatives,
                "alternativa_seleccionada": selected,
            }
            save(project, "M1", "Solicitud y alternativas actualizadas", selected)
            st.rerun()
    ai_panel(project, "M1")


def render_m2(project: dict[str, Any]) -> None:
    data = project.get("m2", {})
    st.caption(f"Alternativa seleccionada: {project.get('m1', {}).get('alternativa_seleccionada', 'Pendiente')}")
    c1, c2 = st.columns(2)
    specialty = c1.text_input("Producto / servicio / especialidad", data.get("especialidad", ""), key=f"m2_sp_{project['folio']}")
    location = c2.text_input("Ubicación", data.get("ubicacion", ""), key=f"m2_loc_{project['folio']}")
    requirements = st.text_area("Requisitos técnicos", data.get("requisitos", ""), key=f"m2_req_{project['folio']}")
    rows = [
        {
            "nombre": row.get("nombre", ""),
            "clasificacion": row.get("clasificacion", "Sin información suficiente"),
            "coincidencia": row.get("justificacion", ""),
            "riesgo": row.get("riesgo", {}).get("nivel", "Pendiente"),
            "justificacion_riesgo": row.get("riesgo", {}).get("justificacion", ""),
        }
        for row in data.get("proveedores", [])
    ] or [{"nombre": "", "clasificacion": "Sin información suficiente", "coincidencia": "", "riesgo": "Pendiente", "justificacion_riesgo": ""}]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "clasificacion": st.column_config.SelectboxColumn(
                "Clasificación",
                options=["Recomendado para invitar", "Requiere validación adicional", "No recomendado", "Sin información suficiente"],
            ),
            "riesgo": st.column_config.SelectboxColumn("Riesgo", options=["Pendiente", "Bajo", "Medio", "Alto"]),
        },
        key=f"m2_providers_{project['folio']}",
    )
    cleaned = normalize_rows(edited)
    names = [str(row["nombre"]).strip() for row in cleaned if str(row.get("nombre", "")).strip()]
    current = data.get("proveedor_recomendado", "")
    selected = st.selectbox(
        "Proveedor recomendado",
        [""] + names,
        index=([""] + names).index(current) if current in names else 0,
        key=f"m2_selected_{project['folio']}",
    )
    if st.button("Guardar módulo 2", type="primary", key=f"m2_save_{project['folio']}"):
        if not names or not selected:
            st.warning("Agrega al menos un proveedor y selecciona el recomendado.")
        else:
            providers = [
                {
                    "nombre": str(row["nombre"]).strip(),
                    "clasificacion": row.get("clasificacion", "Sin información suficiente"),
                    "justificacion": str(row.get("coincidencia", "")).strip(),
                    "riesgo": {
                        "nivel": row.get("riesgo", "Pendiente"),
                        "justificacion": str(row.get("justificacion_riesgo", "")).strip(),
                    },
                }
                for row in cleaned
                if str(row.get("nombre", "")).strip()
            ]
            project["m2"] = {
                "estado": "completo",
                "especialidad": specialty,
                "ubicacion": location,
                "requisitos": requirements,
                "proveedores": providers,
                "proveedor_recomendado": selected,
            }
            save(project, "M2", "Proveedores actualizados", selected)
            st.rerun()
    ai_panel(project, "M2")


def render_m3(project: dict[str, Any]) -> None:
    data = project.get("m3", {})
    statuses = ["No iniciado", "En proceso", "Precalificado", "Condicionado", "Rechazado"]
    c1, c2 = st.columns(2)
    status = c1.selectbox(
        "Estatus de precalificación",
        statuses,
        index=statuses.index(data.get("estatus", "No iniciado")) if data.get("estatus", "No iniciado") in statuses else 0,
        key=f"m3_status_{project['folio']}",
    )
    score = c2.number_input("Score", min_value=0, max_value=100, value=int(data.get("score", 0) or 0), key=f"m3_score_{project['folio']}")
    notes = st.text_area("Documentación faltante / observaciones", data.get("observaciones", ""), key=f"m3_notes_{project['folio']}")
    if st.button("Guardar módulo 3", type="primary", key=f"m3_save_{project['folio']}"):
        project["m3"] = {"estado": "completo", "estatus": status, "score": score, "observaciones": notes}
        save(project, "M3", "Precalificación actualizada", status)
        st.rerun()
    ai_panel(project, "M3")


def render_m4(project: dict[str, Any]) -> None:
    data = project.get("m4", {})
    rows = [
        {
            "categoria": label,
            "nivel": data.get("categorias", {}).get(key, {}).get("nivel", "Pendiente"),
            "justificacion": data.get("categorias", {}).get(key, {}).get("justificacion", ""),
        }
        for key, label in CATEGORIES
    ]
    edited = st.data_editor(
        rows,
        use_container_width=True,
        disabled=["categoria"],
        column_config={"nivel": st.column_config.SelectboxColumn("Nivel", options=["Pendiente", "Bajo", "Medio", "Alto"])},
        key=f"m4_categories_{project['folio']}",
    )
    impact = st.text_area("Impacto potencial", data.get("impacto_potencial", ""), key=f"m4_impact_{project['folio']}")
    actions = st.text_area(
        "Acciones preventivas (una por línea)",
        "\n".join(data.get("acciones_preventivas", [])),
        key=f"m4_actions_{project['folio']}",
    )
    alerts = st.text_area("Alertas (una por línea)", "\n".join(data.get("alertas", [])), key=f"m4_alerts_{project['folio']}")
    if st.button("Guardar módulo 4", type="primary", key=f"m4_save_{project['folio']}"):
        edited_rows = normalize_rows(edited)
        if any(row.get("nivel") == "Pendiente" for row in edited_rows):
            st.warning("Asigna un nivel a las siete categorías.")
        else:
            categories = {
                key: {
                    "nivel": edited_rows[index]["nivel"],
                    "justificacion": str(edited_rows[index].get("justificacion", "")).strip(),
                }
                for index, (key, _) in enumerate(CATEGORIES)
            }
            project["m4"] = {
                "estado": "completo",
                "categorias": categories,
                "impacto_potencial": impact,
                "acciones_preventivas": [line.strip() for line in actions.splitlines() if line.strip()],
                "alertas": [line.strip() for line in alerts.splitlines() if line.strip()],
            }
            level = global_risk(project)
            project["m4"]["riesgo_global"] = level
            project["m4"]["recomendacion_final"] = recommendation(level)
            save(project, "M4", "Riesgo consolidado actualizado", level)
            st.rerun()
    current = global_risk(project)
    st.markdown(f"**Riesgo global actual:** {risk_html(current)}", unsafe_allow_html=True)
    st.write(f"**Recomendación:** {recommendation(current)}")
    ai_panel(project, "M4")


def render_m5(project: dict[str, Any]) -> None:
    data = project.get("m5", {})
    c1, c2 = st.columns(2)
    reference = c1.text_input("Precio o índice de referencia", data.get("precio_referencia", ""), key=f"m5_price_{project['folio']}")
    date = c2.date_input("Fecha de consulta", key=f"m5_date_{project['folio']}")
    source = st.text_input("Fuente o vínculo", data.get("fuente", ""), key=f"m5_source_{project['folio']}")
    drivers = st.text_area("Commodities y drivers identificados", data.get("drivers", ""), key=f"m5_drivers_{project['folio']}")
    forecast = st.text_area("Tendencia / forecast de 12 meses", data.get("forecast", ""), key=f"m5_forecast_{project['folio']}")
    if st.button("Guardar módulo 5", type="primary", key=f"m5_save_{project['folio']}"):
        project["m5"] = {
            "estado": "completo",
            "precio_referencia": reference,
            "fecha_consulta": date.isoformat(),
            "fuente": source,
            "drivers": drivers,
            "forecast": forecast,
        }
        save(project, "M5", "Análisis de mercado actualizado", reference)
        st.rerun()
    ai_panel(project, "M5")


def render_m6(project: dict[str, Any]) -> None:
    data = project.get("m6", {})
    rows = data.get("cotizaciones", []) or [
        {"proveedor": project.get("m2", {}).get("proveedor_recomendado", ""), "monto": "", "moneda": "MXN", "plazo": "", "condiciones": ""}
    ]
    edited = st.data_editor(
        rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={"moneda": st.column_config.SelectboxColumn("Moneda", options=["MXN", "USD", "EUR", "Otra"])},
        key=f"m6_quotes_{project['folio']}",
    )
    comparison = st.text_area("Comparación de cotizaciones", data.get("comparacion", ""), key=f"m6_compare_{project['folio']}")
    final = st.text_area("Recomendación integral final", data.get("recomendacion_integral", ""), key=f"m6_final_{project['folio']}")
    next_action = st.text_input("Próxima acción", data.get("proxima_accion", ""), key=f"m6_next_{project['folio']}")
    if st.button("Guardar módulo 6", type="primary", key=f"m6_save_{project['folio']}"):
        if not final.strip():
            st.warning("Escribe la recomendación integral final.")
        else:
            project["m6"] = {
                "estado": "completo",
                "cotizaciones": normalize_rows(edited),
                "comparacion": comparison,
                "recomendacion_integral": final,
                "proxima_accion": next_action,
            }
            project["pendientes"] = [next_action] if next_action.strip() else []
            save(project, "M6", "Cotizaciones y recomendación actualizadas", next_action)
            st.rerun()
    ai_panel(project, "M6")


def render_project(project: dict[str, Any]) -> None:
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown(f'<p class="capex-title">{project["nombre"]}</p>', unsafe_allow_html=True)
        st.caption(f"{project['folio']} · Responsable: {project.get('comprador') or 'Sin asignar'}")
    with c2:
        st.metric("Avance", f"{progress(project)}%")
    st.progress(progress(project) / 100)
    st.markdown(
        f"**Riesgo:** {risk_html(global_risk(project))} &nbsp;&nbsp; **Estatus:** {project.get('estatus', 'Activo')}",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["1. Solicitud", "2. Proveedores", "3. Precalificación", "4. Riesgos", "5. Mercado", "6. Cotizaciones", "Memoria", "Archivo"])
    with tabs[0]:
        render_m1(project)
    with tabs[1]:
        render_m2(project)
    with tabs[2]:
        render_m3(project)
    with tabs[3]:
        render_m4(project)
    with tabs[4]:
        render_m5(project)
    with tabs[5]:
        render_m6(project)
    with tabs[6]:
        st.subheader("Memoria del proyecto")
        if project.get("ia_history"):
            st.write("**Respuestas de IA guardadas**")
            for item in reversed(project["ia_history"]):
                with st.expander(f"{item['modulo']} · {item['fecha'][:16].replace('T', ' ')}"):
                    st.write(item["respuesta"])
        st.write("**Historial de cambios**")
        st.dataframe(project.get("history", []), use_container_width=True, hide_index=True)
    with tabs[7]:
        archive_project(project)


def archive_project(project: dict[str, Any]) -> None:
    st.subheader("Respaldo y archivo")
    payload = json.dumps(project, ensure_ascii=False, indent=2)
    st.download_button(
        "Descargar expediente completo (.json)",
        payload,
        file_name=f"{project['folio']}_expediente.json",
        mime="application/json",
        key=f"download_archive_{project['folio']}",
    )
    if project.get("estatus") != "Archivado":
        st.caption("Descarga el respaldo y guárdalo en la carpeta corporativa antes de archivar.")
        confirm = st.checkbox("Confirmo que descargué el respaldo", key=f"archive_confirm_{project['folio']}")
        if st.button("Marcar como archivado", disabled=not confirm, key=f"archive_{project['folio']}"):
            project["estatus"] = "Archivado"
            project["fecha_archivo"] = now_iso()
            save(project, "Archivo", "Proyecto archivado")
            st.rerun()
    else:
        st.success("Este proyecto está archivado. El expediente completo sigue disponible.")
        if st.button("Reactivar proyecto", key=f"reactivate_{project['folio']}"):
            project["estatus"] = "Activo"
            save(project, "Archivo", "Proyecto reactivado")
            st.rerun()
        st.warning("La depuración de detalle se habilitará después de validar el flujo de respaldo para evitar pérdidas accidentales.")


def new_project_dialog(projects: list[dict[str, Any]]) -> None:
    st.subheader("Nueva solicitud CAPEX")
    with st.form("new_project", clear_on_submit=True):
        proposed = next_folio(projects)
        folio = st.text_input("Folio", proposed)
        name = st.text_input("Nombre del proyecto")
        buyer = st.text_input("Responsable")
        amount = st.text_input("Monto estimado")
        submitted = st.form_submit_button("Crear expediente", type="primary")
    if submitted:
        if not folio.strip() or not name.strip():
            st.warning("El folio y el nombre son obligatorios.")
        elif db.get_project(folio.strip()):
            st.error("Ese folio ya existe.")
        else:
            project = blank_project(folio.strip(), name.strip(), buyer.strip(), amount.strip())
            db.save_project(project)
            st.session_state["selected_folio"] = project["folio"]
            st.session_state["page"] = "Proyecto"
            st.rerun()


def import_project() -> None:
    st.subheader("Restaurar expediente")
    uploaded = st.file_uploader("Selecciona un respaldo .json", type=["json"])
    if uploaded and st.button("Restaurar", type="primary"):
        try:
            project = json.loads(uploaded.getvalue().decode("utf-8"))
            if not isinstance(project, dict) or not project.get("folio") or not project.get("nombre"):
                raise ValueError("Estructura incompleta")
            project["updated_at"] = now_iso()
            add_history(project, "Archivo", "Expediente restaurado")
            db.save_project(project)
            st.session_state["selected_folio"] = project["folio"]
            st.session_state["page"] = "Proyecto"
            st.success("Expediente restaurado correctamente.")
            st.rerun()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            st.error(f"El archivo no es un respaldo válido: {exc}")


projects = all_projects()
with st.sidebar:
    st.markdown("## Copiloto CAPEX")
    if db.mode == "firestore":
        st.markdown('<div class="memory-ok">● Memoria compartida activa</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="memory-local">● Memoria local de prueba</div>', unsafe_allow_html=True)
        st.caption("Cuando configuremos Firestore, tú y tu jefe verán la misma información.")

    page = st.radio(
        "Navegación",
        ["Dashboard", "Proyecto", "Nueva solicitud", "Restaurar respaldo"],
        index=["Dashboard", "Proyecto", "Nueva solicitud", "Restaurar respaldo"].index(st.session_state.get("page", "Dashboard")),
    )
    st.session_state["page"] = page

    project_labels = {
        f"{p['folio']} · {p['nombre']}": p["folio"]
        for p in projects
        if p.get("estatus") != "Archivado"
    }
    if project_labels:
        labels = list(project_labels)
        current_folio = st.session_state.get("selected_folio")
        current_label = next((label for label, folio in project_labels.items() if folio == current_folio), labels[0])
        selected_label = st.selectbox("Abrir proyecto", labels, index=labels.index(current_label))
        st.session_state["selected_folio"] = project_labels[selected_label]
        if st.button("Abrir expediente", use_container_width=True):
            st.session_state["page"] = "Proyecto"
            st.rerun()

if page == "Dashboard":
    render_dashboard(projects)
elif page == "Nueva solicitud":
    new_project_dialog(projects)
elif page == "Restaurar respaldo":
    import_project()
else:
    folio = st.session_state.get("selected_folio")
    project = db.get_project(folio) if folio else None
    if project:
        render_project(project)
    else:
        st.info("Selecciona o crea un proyecto.")
