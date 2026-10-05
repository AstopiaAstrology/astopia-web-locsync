import argparse
import json
import sys
from .core import load_config, sync, validate


def main():
    parser = argparse.ArgumentParser(prog="webloc")
    parser.add_argument("op", choices=["push", "pull", "seed", "validate"])
    parser.add_argument("--config", default="webloc.config.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--base-source", help="base branch en.json for PR validation")
    parser.add_argument("--skip-fallback", action="store_true")
    args = parser.parse_args()
    try:
        if (args.strict or args.local_only or args.base_source) and args.op != "validate":
            parser.error("validation flags require validate")
        if args.skip_fallback and args.op != "seed":
            parser.error("--skip-fallback requires seed")
        config = load_config(args.config)
        if args.op == "validate":
            result, code = validate(config, args.strict, args.local_only, args.base_source)
        else:
            result, code = sync(config, args.op, args.skip_fallback), 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except Exception as exc:
        # API/credential exceptions can contain sensitive request material.
        print(json.dumps({"error": str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else type(exc).__name__}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
