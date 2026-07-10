"""Interfaz de linea de comandos de Atlas.

Subcomandos:
  generate   genera el dataset sintetico de eventos (JSONL)
  signals    calcula las señales deterministas y las exporta (CSV + resumen JSON)
  detect     ejecuta la baseline de secretos y reporta precision/recall vs ground truth

Ejemplos:
  python -m atlas.cli generate --out data/events.jsonl
  python -m atlas.cli signals --events data/events.jsonl --out data/signals
  python -m atlas.cli detect --events data/events.jsonl --out data/detection.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import config, dashboard as dashboard_mod, doctor as doctor_mod, storage
from . import validation as validation_mod
from .analysis import artifact as artifact_mod
from .analysis import boilerplate as boilerplate_mod
from .analysis import brief as brief_mod
from .analysis import chat as chat_mod
from .analysis import classifier, policy as policy_mod, secrets_llm
from .detection import baseline
from .generation.generator import generate_events
from .llm import describe_provider, get_provider
from .signals import aggregations


def _cmd_generate(args: argparse.Namespace) -> None:
    sim = config.SIMULATION
    if args.seed is not None:
        sim = config.SimulationConfig(seed=args.seed)
    events = generate_events(sim=sim)
    n = storage.write_events_jsonl(events, args.out)
    print(f"Generados {n} eventos en {args.out} (semilla {sim.seed})")


def _cmd_signals(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    signals = aggregations.compute_all_signals(df)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = signals.pop("summary")
    for name, table in signals.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Señales exportadas a {out_dir}/ ({len(signals)} tablas)")
    print("Resumen:", json.dumps(summary, ensure_ascii=False))


def _cmd_detect(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    report = baseline.evaluate_baseline(df)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Baseline de secretos: precision {report['precision']}, "
        f"recall {report['recall']}, F1 {report['f1']}"
    )
    print(f"Secretos escapados (los que cazara el LLM): {len(report['missed_secrets'])}")
    print(f"Informe completo en {args.out}")


def _cmd_classify_eval(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    print(f"Evaluando clasificador (reglas vs IA) sobre {args.per_category} prompts por categoria...")
    report = classifier.evaluate_classifiers(provider, df, per_category=args.per_category, seed=args.seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Reglas: {report['rule_accuracy']:.0%} acierto ({report['rule_correct']}/{report['n']}) | "
        f"IA: {report['llm_accuracy']:.0%} acierto ({report['llm_correct']}/{report['n']})"
    )
    print(f"Detalle en {args.out}")


def _cmd_secrets_eval(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    print(f"Evaluando deteccion de secretos (baseline vs IA) sobre positivos mas {args.neg_sample} negativos...")
    report = secrets_llm.evaluate_secret_detection(provider, df, neg_sample=args.neg_sample, seed=args.seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    b, l = report["baseline"], report["llm"]
    print(f"Baseline: recall {b['recall']}, precision {b['precision']}, F1 {b['f1']}")
    print(f"IA:       recall {l['recall']}, precision {l['precision']}, F1 {l['f1']}")
    print(f"Secretos que SOLO caza la IA: {len(report['caught_by_llm_only'])}")
    for item in report["caught_by_llm_only"]:
        print(f"  - [{item['gt_secret_type']}] {item['team']}: {item['prompt_text'][:80]}")
    print(f"Detalle en {args.out}")


def _cmd_brief(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    signals = aggregations.compute_all_signals(df)
    extras = brief_mod.gather_extras(df)
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    print("Generando el brief ejecutivo de gobernanza...")
    brief = brief_mod.generate_brief(provider, signals, extras)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = out.with_suffix(".md")
    md_path.write_text(brief_mod.render_markdown(brief), encoding="utf-8")
    print(f"Brief guardado en {out} y {md_path}")
    print()
    print(brief_mod.render_markdown(brief))


def _cmd_boilerplate(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    provider = None
    if not args.no_llm:
        provider = get_provider()
        print(f"Proveedor LLM: {describe_provider(provider)}")
    print(f"Detectando boilerplate en el equipo {args.team} (clustering lexico TF-IDF)...")
    report = boilerplate_mod.analyze_team(df, args.team, provider=provider)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    v = report["validation_vs_gt"]
    print(
        f"Detectado {report['detected_pct']}% del equipo como boilerplate en "
        f"{report['clusters_found']} clusters. Validacion vs ground truth: "
        f"precision {v['precision']}, recall {v['recall']}"
    )
    if report["clusters"]:
        top = report["clusters"][0]
        print(
            f"Cluster mayor: {top['size']} prompts, {top['share_pct']}% del equipo, "
            f"coste {top['cluster_cost_eur']} EUR, ahorro estimado {top['estimated_savings_eur']} EUR"
        )
        if top.get("llm_summary"):
            s = top["llm_summary"]
            print(f"Patron (IA): {s.get('nombre_patron')}")
            print(f"Plantilla sugerida (IA): {s.get('plantilla_sugerida')}")
    print(f"Detalle en {args.out}")


def _cmd_artifact(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    limits = aggregations.recommended_weekly_limits(df)

    brief = None
    signed_by = "Atlas (heuristica determinista)"
    if args.brief and Path(args.brief).exists():
        brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
        meta = brief.get("_meta", {})
        signed_by = f"Atlas via {meta.get('provider', '?')}:{meta.get('model', '?')}"

    proposal = artifact_mod.build_limit_proposal(
        limits, generated_at=datetime.now().isoformat(timespec="seconds"), signed_by=signed_by, brief=brief
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(artifact_mod.render_markdown(proposal), encoding="utf-8")
    artifact_mod.to_csv_rows(proposal).to_csv(out.with_suffix(".csv"), index=False)
    print(f"Artefacto generado en {out}, {out.with_suffix('.md')} y {out.with_suffix('.csv')}")
    print()
    print(artifact_mod.render_markdown(proposal))


def _cmd_policy(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    pol = policy_mod.load_policy(args.policy)
    result = policy_mod.evaluate(df, pol)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Cumplimiento global: {result['cumplimiento_pct']}% "
        f"({result['incumplimientos']} incumplimientos de {result['comprobaciones']} comprobaciones)"
    )
    for v in result["violaciones"]:
        print(f"  [{v['severidad']:7s}] {v['equipo']}: {v['detalle']}")
    print(f"Detalle en {out}")


def _cmd_chat(args: argparse.Namespace) -> None:
    df = aggregations.load_dataframe(args.events)
    if df.empty:
        print("No hay eventos que procesar.")
        return
    signals = aggregations.compute_all_signals(df)
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    result = chat_mod.answer(provider, signals, df, args.question)
    print(f"\nPregunta: {args.question}")
    print(f"(herramienta: {result['tool']})")
    print(f"\n{result['answer']}")


def _cmd_validate_secrets(args: argparse.Namespace) -> None:
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    print("Evaluando deteccion de secretos sobre el set gold (herramienta vs LLM)...")
    rep = validation_mod.evaluate_secrets(provider)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    b, l, nl, hn = rep["baseline"], rep["llm"], rep["lenguaje_natural"], rep["negativos_dificiles"]
    print(f"  {rep['n']} casos ({rep['positivos']} positivos)")
    print(f"  Baseline (herramienta): recall {b['recall']}, precision {b['precision']}, F1 {b['f1']}")
    print(f"  LLM:                    recall {l['recall']}, precision {l['precision']}, F1 {l['f1']}")
    print(f"  Recall en lenguaje natural: baseline {nl['recall_baseline']} vs LLM {nl['recall_llm']}")
    print(f"  Falsos positivos en negativos dificiles: baseline {hn['falsos_positivos_baseline']} vs LLM {hn['falsos_positivos_llm']} (de {hn['n']})")
    print(f"  Detalle en {args.out}")


def _cmd_validate_intent(args: argparse.Namespace) -> None:
    provider = get_provider()
    print(f"Proveedor LLM: {describe_provider(provider)}")
    print("Evaluando clasificacion de intencion sobre el set gold (reglas vs LLM)...")
    rep = validation_mod.evaluate_intent(provider)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {rep['n']} casos. Reglas: {rep['rule_accuracy']:.0%} | LLM: {rep['llm_accuracy']:.0%}")
    for lang, b in rep["por_idioma"].items():
        print(f"    {lang}: reglas {b['rule_accuracy']:.0%} | LLM {b['llm_accuracy']:.0%} (n={b['n']})")
    print(f"  Detalle en {args.out}")


def _cmd_validate_pii(args: argparse.Namespace) -> None:
    rep = validation_mod.evaluate_pii()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    h, s = rep["herramienta"], rep["senuelos"]
    print("Detección de PII estructurada (solo herramienta, regla + checksum):")
    print(f"  {rep['n']} casos ({rep['positivos']} positivos)")
    print(f"  Precisión {h['precision']}, recall {h['recall']}, F1 {h['f1']}")
    print(f"  Aciertos de tipo: {rep['errores_de_tipo']} errores")
    print(f"  Señuelos con checksum inválido: {s['falsos_positivos']} falsos positivos de {s['n']}")
    print(f"  Detalle en {args.out}")


def _cmd_export_dashboard(args: argparse.Namespace) -> None:
    data = dashboard_mod.export(args.events, args.out, args.data_dir, args.policy)
    print(f"Dashboard data exportado a {args.out}")
    print(
        f"  {data['meta']['events']} eventos, {data['meta']['teams']} equipos, "
        f"coste {data['meta']['total_cost_eur']} EUR, modelo {data['meta']['model']}"
    )
    secciones = [k for k in ("brief", "policy", "anomaly", "savings", "evidence", "nl_secret") if data.get(k)]
    print(f"  Secciones con datos: {', '.join(secciones)}")


def _cmd_doctor(args: argparse.Namespace) -> None:
    checks = doctor_mod.run_checks(args.events, args.data_dir, args.policy)
    print("Atlas doctor: invariantes de la demo")
    print(doctor_mod.format_report(checks))
    if not all(c.ok for c in checks):
        raise SystemExit(1)


def _cmd_snapshot(args: argparse.Namespace) -> None:
    """Congela el data.{js,json} actual como snapshot de respaldo versionado."""
    src_dir = Path(args.dashboard_dir)
    pairs = [("data.json", "data.demo.json"), ("data.js", "data.demo.js")]
    done = []
    for src, dst in pairs:
        s = src_dir / src
        if s.exists():
            shutil.copyfile(s, src_dir / dst)
            done.append(dst)
    if not done:
        print(f"No hay data.js/data.json en {src_dir}. Ejecuta antes 'atlas export-dashboard'.")
        raise SystemExit(1)
    print(f"Snapshot de respaldo creado: {', '.join(done)} (versionado, fallback del dashboard)")


def _cmd_scan(args: argparse.Namespace) -> None:
    """Analiza un texto libre: reglas, checksum (PII) e IA local. La demo en vivo."""
    from .analysis import secrets_llm
    from .detection import pii
    from .llm.base import LLMError

    # stdin es la via recomendada: evita dejar el secreto en el historial del
    # shell o visible en la lista de procesos. El posicional sigue funcionando
    # para conservar compatibilidad con los ejemplos y scripts existentes.
    text = args.text if args.text is not None else sys.stdin.read()
    if not text:
        raise SystemExit("No se recibio texto para analizar por argumento ni por stdin.")
    print(f"Entrada analizada: {len(text)} caracteres (contenido oculto)\n")

    findings = baseline.detect_secrets_in_text(text)
    btypes = sorted({f.secret_type for f in findings})
    print("  Reglas + detect-secrets :", f"detectado ({', '.join(btypes)})" if findings else "no lo ve")

    hits = pii.detect_pii(text)
    labels = {"iban": "IBAN", "dni": "DNI/NIE", "tarjeta": "tarjeta", "email": "email"}
    det = ", ".join(f"{labels.get(h['type'], h['type'])} {h['valor']}" for h in hits)
    print("  Checksum (IBAN/DNI/...)  :", det if hits else "sin dato estructurado")

    try:
        provider = get_provider()
        # strict=True: si el LLM falla (modelo no descargado, timeout), debe
        # verse 'modelo no disponible', nunca un falso 'no detecta secreto'.
        llm = secrets_llm.llm_detect_secret(provider, text, strict=True)
        if llm.get("contains_secret"):
            # La evidencia del modelo puede repetir el secreto: nunca se muestra.
            safe_types = {"password", "api_key", "connection_string", "pii"}
            secret_type = llm.get("secret_type")
            extra = (
                f": {secret_type}"
                if isinstance(secret_type, str) and secret_type in safe_types
                else ""
            )
            print(f"  IA local                : secreto detectado{extra}")
        else:
            print("  IA local                : no detecta secreto")
    except LLMError:
        # Algunos errores de parseo incluyen parte de la respuesta del modelo,
        # que a su vez puede contener la entrada sensible.
        print("  IA local                : modelo no disponible")


def _cmd_serve(args: argparse.Namespace) -> None:
    from .server import serve

    serve(args.dashboard_dir, args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas", description="Atlas: gobierno del uso de IA")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="genera el dataset sintetico")
    g.add_argument("--out", default="data/events.jsonl", help="ruta de salida JSONL")
    g.add_argument("--seed", type=int, default=None, help="semilla (por defecto la de config)")
    g.set_defaults(func=_cmd_generate)

    s = sub.add_parser("signals", help="calcula y exporta las señales")
    s.add_argument("--events", default="data/events.jsonl", help="ruta del JSONL de eventos")
    s.add_argument("--out", default="data/signals", help="directorio de salida")
    s.set_defaults(func=_cmd_signals)

    d = sub.add_parser("detect", help="ejecuta la baseline de secretos")
    d.add_argument("--events", default="data/events.jsonl", help="ruta del JSONL de eventos")
    d.add_argument("--out", default="data/detection.json", help="ruta del informe JSON")
    d.set_defaults(func=_cmd_detect)

    ce = sub.add_parser("classify-eval", help="contraste reglas vs IA en clasificacion de tareas")
    ce.add_argument("--events", default="data/events.jsonl")
    ce.add_argument("--per-category", type=int, default=3, help="prompts por categoria a evaluar")
    ce.add_argument("--seed", type=int, default=0)
    ce.add_argument("--out", default="data/classify_eval.json")
    ce.set_defaults(func=_cmd_classify_eval)

    se = sub.add_parser("secrets-eval", help="contraste baseline vs IA en deteccion de secretos")
    se.add_argument("--events", default="data/events.jsonl")
    se.add_argument("--neg-sample", type=int, default=20, help="numero de negativos a muestrear")
    se.add_argument("--seed", type=int, default=0)
    se.add_argument("--out", default="data/secrets_eval.json")
    se.set_defaults(func=_cmd_secrets_eval)

    br = sub.add_parser("brief", help="genera el brief ejecutivo de gobernanza (el agente)")
    br.add_argument("--events", default="data/events.jsonl")
    br.add_argument("--out", default="data/brief.json")
    br.set_defaults(func=_cmd_brief)

    bp = sub.add_parser("boilerplate", help="detecta boilerplate repetido y sintetiza la plantilla")
    bp.add_argument("--events", default="data/events.jsonl")
    bp.add_argument("--team", default="Datos", help="equipo a analizar")
    bp.add_argument("--no-llm", action="store_true", help="solo deteccion, sin sintesis LLM")
    bp.add_argument("--out", default="data/boilerplate.json")
    bp.set_defaults(func=_cmd_boilerplate)

    ar = sub.add_parser("artifact", help="genera la propuesta de limites firmada (artefacto descargable)")
    ar.add_argument("--events", default="data/events.jsonl")
    ar.add_argument("--brief", default="data/brief.json", help="brief del agente para usar sus acciones (opcional)")
    ar.add_argument("--out", default="data/limit_proposal.json")
    ar.set_defaults(func=_cmd_artifact)

    po = sub.add_parser("policy", help="audita la telemetria contra la politica (policy-as-code)")
    po.add_argument("--events", default="data/events.jsonl")
    po.add_argument("--policy", default="policy.yaml", help="ruta de la politica YAML")
    po.add_argument("--out", default="data/policy.json")
    po.set_defaults(func=_cmd_policy)

    ch = sub.add_parser("chat", help="pregunta en lenguaje natural sobre el uso de IA (tool-use)")
    ch.add_argument("question", help="la pregunta, entre comillas")
    ch.add_argument("--events", default="data/events.jsonl")
    ch.set_defaults(func=_cmd_chat)

    vs = sub.add_parser("validate-secrets", help="mide herramienta vs LLM en secretos (set gold)")
    vs.add_argument("--out", default="data/validate_secrets.json")
    vs.set_defaults(func=_cmd_validate_secrets)

    vi = sub.add_parser("validate-intent", help="mide reglas vs LLM en intencion (set gold)")
    vi.add_argument("--out", default="data/validate_intent.json")
    vi.set_defaults(func=_cmd_validate_intent)

    vp = sub.add_parser("validate-pii", help="mide el detector de PII estructurada (set gold)")
    vp.add_argument("--out", default="data/validate_pii.json")
    vp.set_defaults(func=_cmd_validate_pii)

    ed = sub.add_parser("export-dashboard", help="exporta el data.json del dashboard")
    ed.add_argument("--events", default="data/events.jsonl")
    ed.add_argument("--data-dir", default="data", help="directorio con las cache de brief/boilerplate/validacion")
    ed.add_argument("--policy", default="policy.yaml", help="ruta de la politica YAML")
    ed.add_argument("--out", default="dashboard/data.json")
    ed.set_defaults(func=_cmd_export_dashboard)

    dr = sub.add_parser("doctor", help="valida los invariantes de la demo (PASS/FAIL)")
    dr.add_argument("--events", default="data/events.jsonl")
    dr.add_argument("--data-dir", default="data")
    dr.add_argument("--policy", default="policy.yaml", help="ruta de la politica YAML")
    dr.set_defaults(func=_cmd_doctor)

    sn = sub.add_parser("snapshot", help="congela data.{js,json} como respaldo versionado")
    sn.add_argument("--dashboard-dir", default="dashboard")
    sn.set_defaults(func=_cmd_snapshot)

    sc = sub.add_parser("scan", help="analiza un texto (reglas + checksum + IA local): la demo en vivo")
    sc.add_argument(
        "text",
        nargs="?",
        help="texto a analizar; si se omite, se lee de stdin (recomendado)",
    )
    sc.set_defaults(func=_cmd_scan)

    sv = sub.add_parser("serve", help="sirve el dashboard estatico en local")
    sv.add_argument("--dashboard-dir", default="dashboard")
    sv.add_argument("--port", type=int, default=8777)
    sv.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
