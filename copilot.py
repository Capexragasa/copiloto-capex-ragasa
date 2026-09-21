from __future__ import annotations

import json
from typing import Any

from risk import global_risk, selected_alternative, selected_supplier


MODULE_TASKS = {
    "M1": "Evalúa la solicitud, detecta faltantes y propone alternativas técnicas con riesgo Bajo/Medio/Alto y justificación.",
    "M2": "Evalúa únicamente los proveedores listados, justifica su coincidencia técnica y clasifica su riesgo. No inventes datos.",
    "M3": "Revisa la precalificación registrada e indica qué documentación o validaciones faltan.",
    "M4": "Consolida commodities, tipo de cambio, inflación, amortización, financiero, incumplimiento y dependencia. Propón mitigaciones.",
    "M5": "Analiza el precio o índice de mercado aportado, sus drivers y el posible comportamiento a 12 meses. Señala fuentes y fecha.",
    "M6": "Compara las cotizaciones junto con el riesgo acumulado y emite una recomendación integral trazable.",
}


def project_context(project: dict[str, Any]) -> str:
    alternative = selected_alternative(project) or {}
    supplier = selected_supplier(project) or {}
    compact = {
        "folio": project.get("folio"),
        "proyecto": project.get("nombre"),
        "responsable": project.get("comprador"),
        "monto_estimado": project.get("monto_estimado"),
        "estatus": project.get("estatus"),
        "descripcion": project.get("m1", {}).get("descripcion"),
        "area": project.get("m1", {}).get("area"),
        "criticidad": project.get("m1", {}).get("criticidad"),
        "informacion_tecnica": project.get("m1", {}).get("info_tecnica"),
        "alternativa_seleccionada": alternative,
        "proveedor_recomendado": supplier,
        "precalificacion": project.get("m3", {}),
        "riesgo_consolidado": project.get("m4", {}),
        "mercado": project.get("m5", {}),
        "cotizaciones": project.get("m6", {}).get("cotizaciones", []),
        "riesgo_global_actual": global_risk(project),
        "pendientes": project.get("pendientes", []),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def build_prompt(project: dict[str, Any], module: str) -> str:
    task = MODULE_TASKS[module]
    return f"""Actúa como Copiloto de Compras CAPEX de Ragasa. Trabaja únicamente con la información proporcionada. No inventes precios, certificaciones, historial, indicadores ni fuentes. Si falta evidencia, indícalo claramente.

CONTEXTO DEL EXPEDIENTE
{project_context(project)}

TAREA {module}
{task}

ENTREGA EN ESPAÑOL DE MÉXICO
1. Resumen ejecutivo breve.
2. Datos faltantes críticos.
3. Análisis solicitado con justificación.
4. Riesgos identificados.
5. Acciones concretas para avanzar a verde.
6. Próxima acción recomendada.

Al final agrega una sección titulada REGISTRO PARA EL EXPEDIENTE, lista para copiar y guardar en el sistema."""
