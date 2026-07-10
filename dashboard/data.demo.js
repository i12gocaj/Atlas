window.ATLAS_DATA = {
  "meta": {
    "events": 6826,
    "sessions": 4350,
    "weeks": 8,
    "teams": 5,
    "users": 17,
    "total_cost_eur": 1113.82,
    "rejected_cost_eur": 673.32,
    "rejected_pct": 60.5,
    "model": "qwen2.5:7b"
  },
  "brief": {
    "resumen_ejecutivo": "El coste de Pagos aumentó significativamente en 2026-W18, pasando a 91.41 EUR (x4.31) desde 21.23 EUR, lo que representa el hallazgo más grave. Se recomienda investigar esta variación para evitar futuros picos de coste.",
    "hallazgos": [
      {
        "id": "anomalia_Pagos",
        "titulo": "Anomalía de coste en Pagos",
        "severidad": "alta",
        "evidencia": "El coste de Pagos pasó de 21.23 a 91.41 EUR en 2026-W18 (x4.31).",
        "ahorro_eur": null,
        "recomendacion": ""
      },
      {
        "id": "ahorro",
        "titulo": "Ahorro recuperable en Pagos",
        "severidad": "media",
        "evidencia": "Pagos usa el modelo caro en 1600 tareas pequeñas; pasarlas al modelo barato ahorraría 84.66 EUR.",
        "ahorro_eur": 84.66,
        "recomendacion": "Migrar tareas pequeñas en Pagos al modelo barato podría ahorrar 84.66 EUR."
      },
      {
        "id": "boilerplate",
        "titulo": "Boilerplate repetido en Datos",
        "severidad": "media",
        "evidencia": "El 36.9% de los eventos de Datos son la misma petición repetida, candidata a una plantilla. Ejemplo: \"Necesito el job de ingesta tipico para saldos, con las columnas de control de…\".",
        "ahorro_eur": null,
        "recomendacion": "Optimizar la petición repetida en Datos mediante el uso de plantillas podría mejorar la eficiencia."
      },
      {
        "id": "adopcion",
        "titulo": "Adopción inmadura en Equipo Nuevo",
        "severidad": "media",
        "evidencia": "Equipo Nuevo tiene la aceptación más baja (0.389), señal de uso poco eficiente de la IA.",
        "ahorro_eur": null,
        "recomendacion": "Incrementar la adopción del equipo Nuevo a través de formación y orientación para optimizar el uso de la IA."
      },
      {
        "id": "secretos",
        "titulo": "Posibles secretos en prompts",
        "severidad": "alta",
        "evidencia": "Se detectaron 4 prompts con posibles secretos en Plataforma (tipos: api_key, connection_string, password).",
        "ahorro_eur": null,
        "recomendacion": "Revisar los prompts en Plataforma con posibles secretos (api_key, connection_string, password) para garantizar la seguridad."
      }
    ],
    "recomendaciones_limite": [
      {
        "equipo": "Pagos",
        "accion": "bajar",
        "motivo": "Anomalía de coste activa. Optimizar el modelo antes de fijar el límite."
      },
      {
        "equipo": "Datos",
        "accion": "subir",
        "motivo": "Uso eficiente y criticidad que justifican algo de margen."
      },
      {
        "equipo": "Equipo Nuevo",
        "accion": "mantener",
        "motivo": "Gasto alineado con el nivel eficiente recomendado."
      },
      {
        "equipo": "Plataforma",
        "accion": "subir",
        "motivo": "Uso eficiente y criticidad que justifican algo de margen."
      },
      {
        "equipo": "Core Banking",
        "accion": "subir",
        "motivo": "Uso eficiente y criticidad que justifican algo de margen."
      }
    ],
    "integrity": {
      "checked": 6,
      "invented": [],
      "ok": true
    },
    "_meta": {
      "provider": "ollama",
      "model": "qwen2.5:7b"
    }
  },
  "policy": {
    "version": 1,
    "reglas_evaluadas": 5,
    "equipos": 5,
    "comprobaciones": 25,
    "incumplimientos": 5,
    "cumplimiento_pct": 80.0,
    "por_equipo": [
      {
        "equipo": "Pagos",
        "incumplimientos": 2,
        "cumplimiento_pct": 60.0
      },
      {
        "equipo": "Plataforma",
        "incumplimientos": 1,
        "cumplimiento_pct": 80.0
      },
      {
        "equipo": "Datos",
        "incumplimientos": 1,
        "cumplimiento_pct": 80.0
      },
      {
        "equipo": "Equipo Nuevo",
        "incumplimientos": 1,
        "cumplimiento_pct": 80.0
      },
      {
        "equipo": "Core Banking",
        "incumplimientos": 0,
        "cumplimiento_pct": 100.0
      }
    ],
    "violaciones": [
      {
        "equipo": "Plataforma",
        "observado": 4,
        "umbral": 0,
        "detalle": "4 prompts con secreto enviados (límite 0).",
        "remediacion": "Bloquear el envío y redactar el secreto antes de salir al proveedor. Formar al equipo: un secreto en un prompt es una fuga.",
        "regla": "cero_secretos",
        "titulo": "Cero secretos a proveedores externos",
        "severidad": "critica"
      },
      {
        "equipo": "Pagos",
        "observado": 97.81,
        "umbral": 50.0,
        "detalle": "5 semanas sobre el techo de 50,00 € (pico 97,81 € en 2026-W19), exceso acumulado 209,17 €.",
        "remediacion": "Revisar el pico: bajar a modelo barato en autocompletado y fijar el límite semanal recomendado para el equipo.",
        "regla": "techo_coste_semanal",
        "titulo": "Techo de coste semanal por equipo",
        "severidad": "alta"
      },
      {
        "equipo": "Equipo Nuevo",
        "observado": 0.389,
        "umbral": 0.5,
        "detalle": "Aceptación 38.9% bajo el mínimo de 50%: el coste de IA no se traduce en valor.",
        "remediacion": "Revisar prompts y dar formación. Acompañar al equipo con ejemplos de buen uso antes de ampliar el gasto.",
        "regla": "aceptacion_minima",
        "titulo": "Aceptación mínima de sugerencias",
        "severidad": "media"
      },
      {
        "equipo": "Pagos",
        "observado": 84.66,
        "umbral": 20.0,
        "detalle": "1600 interacciones triviales en modelo caro, 84,66 € recuperables (límite 20,00 €).",
        "remediacion": "Enrutar las tareas de menos de 700 tokens al modelo barato. El ahorro se estima con las tarifas observadas; valida la calidad antes de desplegar el cambio.",
        "regla": "sin_derroche_modelo",
        "titulo": "Sin modelo caro en tareas triviales",
        "severidad": "media"
      },
      {
        "equipo": "Datos",
        "observado": 36.9,
        "umbral": 20.0,
        "detalle": "36.9% de prompts repetidos (límite 20%): trabajo que debería ser plantilla, no IA.",
        "remediacion": "Convertir las plantillas repetidas en snippets o automatización y reservar la IA para lo que de verdad aporta.",
        "regla": "automatizar_boilerplate",
        "titulo": "Límite de trabajo repetitivo (boilerplate)",
        "severidad": "baja"
      }
    ]
  },
  "scorecard": {
    "weeks": [
      {
        "iso_week": "2026-W15",
        "score": 86.5,
        "seguridad": 75.0,
        "coste": 100.0,
        "eficiencia": 99.9,
        "adopcion": 60.3,
        "fugas": 1,
        "equipos_sobre_techo": 0,
        "derroche_eur": 0.12,
        "aceptacion": 0.603
      },
      {
        "iso_week": "2026-W16",
        "score": 94.1,
        "seguridad": 100.0,
        "coste": 100.0,
        "eficiencia": 99.9,
        "adopcion": 61.1,
        "fugas": 0,
        "equipos_sobre_techo": 0,
        "derroche_eur": 0.09,
        "aceptacion": 0.611
      },
      {
        "iso_week": "2026-W17",
        "score": 93.7,
        "seguridad": 100.0,
        "coste": 100.0,
        "eficiencia": 100.0,
        "adopcion": 57.9,
        "fugas": 0,
        "equipos_sobre_techo": 0,
        "derroche_eur": 0.0,
        "aceptacion": 0.579
      },
      {
        "iso_week": "2026-W18",
        "score": 86.4,
        "seguridad": 100.0,
        "coste": 80.0,
        "eficiencia": 90.3,
        "adopcion": 65.5,
        "fugas": 0,
        "equipos_sobre_techo": 1,
        "derroche_eur": 16.57,
        "aceptacion": 0.655
      },
      {
        "iso_week": "2026-W19",
        "score": 86.3,
        "seguridad": 100.0,
        "coste": 80.0,
        "eficiencia": 90.6,
        "adopcion": 64.3,
        "fugas": 0,
        "equipos_sobre_techo": 1,
        "derroche_eur": 15.76,
        "aceptacion": 0.643
      },
      {
        "iso_week": "2026-W20",
        "score": 78.5,
        "seguridad": 75.0,
        "coste": 80.0,
        "eficiencia": 89.2,
        "adopcion": 64.4,
        "fugas": 1,
        "equipos_sobre_techo": 1,
        "derroche_eur": 17.25,
        "aceptacion": 0.644
      },
      {
        "iso_week": "2026-W21",
        "score": 78.6,
        "seguridad": 75.0,
        "coste": 80.0,
        "eficiencia": 89.9,
        "adopcion": 64.0,
        "fugas": 1,
        "equipos_sobre_techo": 1,
        "derroche_eur": 16.67,
        "aceptacion": 0.64
      },
      {
        "iso_week": "2026-W22",
        "score": 78.2,
        "seguridad": 75.0,
        "coste": 80.0,
        "eficiencia": 88.1,
        "adopcion": 64.2,
        "fugas": 1,
        "equipos_sobre_techo": 1,
        "derroche_eur": 18.39,
        "aceptacion": 0.642
      }
    ],
    "latest": {
      "iso_week": "2026-W22",
      "score": 78.2,
      "seguridad": 75.0,
      "coste": 80.0,
      "eficiencia": 88.1,
      "adopcion": 64.2,
      "fugas": 1,
      "equipos_sobre_techo": 1,
      "derroche_eur": 18.39,
      "aceptacion": 0.642
    },
    "delta_vs_prev": -0.4,
    "delta_vs_inicio": -8.3,
    "pico": {
      "iso_week": "2026-W16",
      "score": 94.1
    },
    "pesos": {
      "seguridad": 0.3,
      "coste": 0.3,
      "eficiencia": 0.25,
      "adopcion": 0.15
    }
  },
  "cost_by_team": [
    {
      "team": "Pagos",
      "cost_eur": 521.37
    },
    {
      "team": "Datos",
      "cost_eur": 205.34
    },
    {
      "team": "Equipo Nuevo",
      "cost_eur": 161.72
    },
    {
      "team": "Plataforma",
      "cost_eur": 116.74
    },
    {
      "team": "Core Banking",
      "cost_eur": 108.65
    }
  ],
  "acceptance_by_team": [
    {
      "team": "Pagos",
      "acceptance_rate": 0.694
    },
    {
      "team": "Plataforma",
      "acceptance_rate": 0.681
    },
    {
      "team": "Core Banking",
      "acceptance_rate": 0.668
    },
    {
      "team": "Datos",
      "acceptance_rate": 0.547
    },
    {
      "team": "Equipo Nuevo",
      "acceptance_rate": 0.389
    }
  ],
  "anomaly": {
    "team": "Pagos",
    "iso_week": "2026-W18",
    "prev_cost": 21.2259,
    "cost_eur": 91.4142,
    "wow_ratio": 4.31
  },
  "spike_team": "Pagos",
  "spike_trend": [
    {
      "iso_week": "2026-W15",
      "cost_eur": 18.63
    },
    {
      "iso_week": "2026-W16",
      "cost_eur": 22.34
    },
    {
      "iso_week": "2026-W17",
      "cost_eur": 21.23
    },
    {
      "iso_week": "2026-W18",
      "cost_eur": 91.41
    },
    {
      "iso_week": "2026-W19",
      "cost_eur": 97.81
    },
    {
      "iso_week": "2026-W20",
      "cost_eur": 89.53
    },
    {
      "iso_week": "2026-W21",
      "cost_eur": 96.33
    },
    {
      "iso_week": "2026-W22",
      "cost_eur": 84.09
    }
  ],
  "team_peaks": [
    {
      "team": "Pagos",
      "peak_eur": 97.81
    },
    {
      "team": "Datos",
      "peak_eur": 28.94
    },
    {
      "team": "Equipo Nuevo",
      "peak_eur": 24.19
    },
    {
      "team": "Plataforma",
      "peak_eur": 16.39
    },
    {
      "team": "Core Banking",
      "peak_eur": 15.34
    }
  ],
  "savings": {
    "team": "Pagos",
    "events": 1600,
    "cost_eur": 96.27,
    "cost_if_cheap": 11.61,
    "savings_eur": 84.66
  },
  "whatif": {
    "spike_team": "Pagos",
    "weeks": 8,
    "actual_total_eur": 1113.82,
    "counterfactual_total_eur": 1029.15,
    "saved_eur": 84.66,
    "saved_annual_low_eur": 330.0,
    "saved_annual_high_eur": 550.0,
    "weekly": [
      {
        "iso_week": "2026-W15",
        "actual": 18.63,
        "counterfactual": 18.51
      },
      {
        "iso_week": "2026-W16",
        "actual": 22.34,
        "counterfactual": 22.34
      },
      {
        "iso_week": "2026-W17",
        "actual": 21.23,
        "counterfactual": 21.23
      },
      {
        "iso_week": "2026-W18",
        "actual": 91.41,
        "counterfactual": 74.84
      },
      {
        "iso_week": "2026-W19",
        "actual": 97.81,
        "counterfactual": 82.04
      },
      {
        "iso_week": "2026-W20",
        "actual": 89.53,
        "counterfactual": 72.28
      },
      {
        "iso_week": "2026-W21",
        "actual": 96.33,
        "counterfactual": 79.65
      },
      {
        "iso_week": "2026-W22",
        "actual": 84.09,
        "counterfactual": 65.81
      }
    ]
  },
  "nl_secret": {
    "team": "Plataforma",
    "user": "diego.romero",
    "text": "El despliegue falla autenticando. Por si acaso, la clave admin es verano2024 y el usuario es deploy_bot. Por que rechaza el login."
  },
  "evidence": {
    "secrets": {
      "tool_recall_nl": 0.0,
      "llm_recall_nl": 1.0,
      "llm_ci": [
        0.824,
        1.0
      ],
      "ci_n": 18,
      "total_n": 46
    },
    "intent": {
      "rule_acc": 0.5,
      "llm_acc": 1.0,
      "llm_ci": [
        0.904,
        1.0
      ],
      "rule_acc_en": 0.333,
      "llm_acc_en": 1.0,
      "n": 36
    },
    "pii": {
      "precision": 1.0,
      "recall": 1.0,
      "n": 24,
      "decoys_n": 4,
      "decoys_fp": 0
    }
  }
};
