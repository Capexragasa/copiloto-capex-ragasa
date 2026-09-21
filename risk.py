from __future__ import annotations

from typing import Any


CATEGORIES = [
    ("commodities", "Commodities"),
    ("tipo_cambio", "Tipo de cambio"),
    ("inflacion", "Inflación"),
    ("amortizacion", "Amortización del equipo"),
    ("financiero", "Financiero"),
    ("incumplimiento", "Incumplimiento"),
    ("dependencia", "Dependencia de proveedor único"),
]

RISK_ORDER = {"Pendiente": -1, "Bajo": 0, "Medio": 1, "Alto": 2}


def selected_alternative(project: dict[str, Any]) -> dict[str, Any] | None:
    m1 = project.get("m1", {})
    selected = m1.get("alternativa_seleccionada")
    return next((a for a in m1.get("alternativas", []) if a.get("nombre") == selected), None)


def selected_supplier(project: dict[str, Any]) -> dict[str, Any] | None:
    m2 = project.get("m2", {})
    selected = m2.get("proveedor_recomendado")
    return next((p for p in m2.get("proveedores", []) if p.get("nombre") == selected), None)


def risk_levels(project: dict[str, Any]) -> list[str]:
    levels: list[str] = []
    request_risk = project.get("m1", {}).get("riesgo_solicitud", {}).get("nivel")
    if request_risk:
        levels.append(request_risk)
    alternative = selected_alternative(project)
    if alternative and alternative.get("riesgo", {}).get("nivel"):
        levels.append(alternative["riesgo"]["nivel"])
    supplier = selected_supplier(project)
    if supplier and supplier.get("riesgo", {}).get("nivel"):
        levels.append(supplier["riesgo"]["nivel"])
    for key, _ in CATEGORIES:
        level = project.get("m4", {}).get("categorias", {}).get(key, {}).get("nivel")
        if level:
            levels.append(level)
    return levels


def global_risk(project: dict[str, Any]) -> str:
    levels = risk_levels(project)
    if not levels:
        return "Pendiente"
    return max(levels, key=lambda value: RISK_ORDER.get(value, -1))


def recommendation(level: str) -> str:
    return {
        "Alto": "No proceder sin mitigación y autorización",
        "Medio": "Proceder con condiciones",
        "Bajo": "Proceder",
    }.get(level, "Pendiente")


def progress(project: dict[str, Any]) -> int:
    complete = sum(
        1 for number in range(1, 7) if project.get(f"m{number}", {}).get("estado") == "completo"
    )
    return round(complete / 6 * 100)
