from pathlib import Path
from .json_io import load, flatten, unflatten, validate_paths, write
from .icu import signature
from .raw import raw_signature
from .sheet import SheetClient, Row


def load_config(path):
    config = load(path)
    if config.get("source_locale") != "en" or config.get("locales") != ["en", "tr", "es", "fr", "pt"]:
        raise ValueError("expected source en and locales en,tr,es,fr,pt")
    if not config.get("tab_prefix", "").startswith("web_"):
        raise ValueError("tab_prefix must start with web_ to isolate Android tabs")
    config["locales_dir"] = str((Path(path).resolve().parent / config["locales_dir"]).resolve())
    policy_path = Path(path).resolve().parent / "webloc.raw-messages.json"
    config["raw_messages"] = load(policy_path) if policy_path.exists() else {}
    return config


def source(config):
    return flatten(load(Path(config["locales_dir"]) / "en.json"))


def indexed(rows):
    result = {}
    for row in rows:
        if row.key in result:
            raise ValueError(f"duplicate Sheet key: {row.key}")
        result[row.key] = row.value
    validate_paths(result)
    return result


def check(messages, reference=None, raw_messages=None):
    raw_messages = raw_messages or {}
    def contract_for(key, value):
        return raw_signature(value, raw_messages[key]) if key in raw_messages else signature(value)
    for key, value in messages.items():
        contract = contract_for(key, value)
        if reference is not None and key in reference and contract != contract_for(key, reference[key]):
            raise ValueError(f"ICU argument/tag mismatch: {key}")


def sync(config, operation, skip_fallback=False, client=None):
    template = load(Path(config["locales_dir"]) / "en.json")
    src = flatten(template)
    check(src, raw_messages=config.get("raw_messages"))
    client = client or SheetClient(config["spreadsheet_id"], read_only=operation == "pull")
    tables, outputs, summary = {}, {}, {}
    for locale in config["locales"]:
        tab = config["tab_prefix"] + locale
        if operation == "seed":
            path = Path(config["locales_dir"]) / f"{locale}.json"
            existing = flatten(load(path)) if path.exists() else {}
            if set(existing) - set(src):
                raise ValueError(f"{locale}: orphan local keys")
        else:
            existing = indexed(client.read_rows(tab))
        values = {}
        for key, text in src.items():
            value = text if locale == "en" else existing.get(key, "")
            if operation == "seed" and skip_fallback and locale != "en" and value == text:
                value = ""
            values[key] = value
        mismatched = []
        for key, value in values.items():
            if not value.strip():
                continue
            try:
                check({key: value}, src, config.get("raw_messages"))
            except ValueError:
                # After a source contract change the old translation stays in the Sheet
                # for the translator to fix; push still delivers the new keys/source.
                if operation != "push":
                    raise
                mismatched.append(key)
        summary[locale] = {"total": len(src), "missing": sum(not v.strip() for v in values.values())}
        if mismatched:
            summary[locale]["contract_mismatch"] = sorted(mismatched)
        if operation == "pull":
            if locale != "en":
                outputs[locale] = unflatten({k: v if v.strip() else src[k] for k, v in values.items()}, template=template)
        else:
            tables[tab] = [Row(k, v) for k, v in sorted(values.items())]
    # Validate every locale before any mutation.
    if operation == "pull":
        for locale, data in outputs.items():
            write(Path(config["locales_dir"]) / f"{locale}.json", data)
    else:
        client.replace_many(tables)
    return {"op": operation, "summary": summary}


def validate(config, strict=False, local_only=False, base_source=None, client=None):
    src = source(config)
    base = flatten(load(base_source)) if base_source else None
    added = set(src) - set(base) if base is not None else set()
    deleted = set(base) - set(src) if base is not None else set()
    changed = {k for k in set(src) & set(base or {}) if src[k] != base[k]}
    errors, warnings = [], []
    unknown_raw = set(config.get("raw_messages", {})) - set(src)
    if unknown_raw:
        errors.append(f"raw policy refers to absent keys: {sorted(unknown_raw)}")
    try:
        check(src, raw_messages=config.get("raw_messages"))
    except ValueError as exc:
        errors.append(f"en: {exc}")
    client = None if local_only else client or SheetClient(config["spreadsheet_id"], read_only=True)
    for locale in config["locales"]:
        datasets = []
        path = Path(config["locales_dir"]) / f"{locale}.json"
        try:
            datasets.append(("local", flatten(load(path))))
            if client:
                datasets.append(("Sheet", indexed(client.read_rows(config["tab_prefix"] + locale))))
        except (ValueError, OSError) as exc:
            errors.append(f"{locale}: {exc}")
        for label, values in datasets:
            orphan = set(values) - set(src)
            tolerated = deleted if label == "Sheet" else set()
            if orphan - tolerated:
                errors.append(f"{locale} {label}: orphan keys {sorted(orphan-tolerated)}")
            missing = {k for k in src if not values.get(k, "").strip()}
            tolerated = added if label == "Sheet" else set()
            if label == "Sheet" and set(src) - set(values) - tolerated:
                errors.append(f"{locale} Sheet: missing rows {sorted(set(src)-set(values)-tolerated)}")
            if missing:
                warnings.append(f"{locale} {label}: {len(missing)} missing/blank translations")
                if strict and missing - tolerated:
                    errors.append(f"{locale} {label}: untranslated keys (strict)")
            for key, value in values.items():
                if key not in src or not value.strip():
                    continue
                try:
                    check({key: value}, src, config.get("raw_messages"))
                except ValueError as exc:
                    if label == "Sheet" and key in changed:
                        warnings.append(f"{locale} Sheet {key}: {exc} (source changed in this PR; fix in Sheet after push)")
                    else:
                        errors.append(f"{locale} {label} {key}: {exc}")
            if label == "Sheet" and locale == "en":
                stale = {k for k in set(src) & set(values) if src[k] != values[k]}
                if stale - changed - added:
                    errors.append(f"en Sheet: stale source values {sorted(stale-changed-added)}")
    return {"op": "validate", "errors": errors, "warnings": warnings,
            "source_changes": {"added": sorted(added), "deleted": sorted(deleted),
                               "changed": sorted(changed)}}, int(bool(errors))
