#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create a new knowledge base on the GPTBots Agent bound to the API key, via the
public Open API — POST /v1/bot/knowledge/base/create.

On success it prints the new `knowledge_base_id`; use that id as the target for
the doc-add endpoints (/v1/bot/doc/text/add, /v1/bot/doc/qa/add,
/v1/bot/doc/spreadsheet/add, …) to populate the base. Curating the source files
first is a separate step — see references/organize-knowledge-base.md.

Endpoint:  POST /v1/bot/knowledge/base/create   (Agent Key)
Base URL:  https://api-{endpoint}.gptbots.ai    (endpoint: sg default / jp / th)

Request body (see references/call-gptbots-api.md):
  name                            (required)  knowledge base name
  desc                            (required)  knowledge base description
  graph_enable                    (optional)  build a knowledge graph (default false)
  access_control_enabled          (optional)  role/doc-level permission filtering (default false)
  kg_ner_extraction_user_prompt   (optional)  triple-extraction prompt; only used when graph_enable

The API key is the target Agent's own key, from its Integration / API channel, and
must match the region endpoint. Pass it via --api-key or the GPTBOTS_API_KEY env
var; the key is never written to disk or logged.

Usage:
  python3 create_knowledge_base.py --name "Product KB" --desc "Manuals + FAQ" --api-key KEY
  GPTBOTS_API_KEY=KEY python3 create_knowledge_base.py --name "KB" --desc "..." --endpoint jp
  python3 create_knowledge_base.py --name "KB" --desc "..." --graph-enable \
      --ner-prompt-file prompt.txt --access-control
  # machine-readable id only:
  python3 create_knowledge_base.py --name "KB" --desc "..." --quiet

Exit codes: 0 ok; 3 API error; 4 usage error.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ERROR_CODES = {
    40000: "parameter error (check name/desc are non-empty)",
    40127: "developer authentication failed — wrong API key or wrong region endpoint",
    20059: "Agent has been deleted",
}


def _base(endpoint):
    return f"https://api-{endpoint}.gptbots.ai"


def _post_json(url, api_key, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode() or "{}")
        except Exception:
            return {"code": e.code, "message": str(e)}
    except urllib.error.URLError as e:
        raise SystemExit(f"network error: {e}")


def _explain(resp):
    """Return an error string, or None on success (knowledge_base_id present)."""
    if resp.get("knowledge_base_id"):
        return None
    code = resp.get("code")
    msg = resp.get("message") or resp.get("msg") or "unknown error"
    return f"code {code}: {ERROR_CODES.get(code, msg)}"


def main(argv):
    ap = argparse.ArgumentParser(
        description="Create a GPTBots knowledge base via the public API")
    ap.add_argument("--name", required=True, help="knowledge base name (required)")
    ap.add_argument("--desc", required=True, help="knowledge base description (required)")
    ap.add_argument("--api-key", default=os.environ.get("GPTBOTS_API_KEY"),
                    help="the Agent's own API key (or set GPTBOTS_API_KEY)")
    ap.add_argument("--endpoint", default="sg", choices=["sg", "jp", "th"],
                    help="region (default sg)")
    ap.add_argument("--graph-enable", action="store_true",
                    help="enable the knowledge graph for this base")
    ap.add_argument("--access-control", action="store_true",
                    help="enable access control (role/doc-level permission filtering)")
    ap.add_argument("--ner-prompt", help="triple-extraction prompt (only used with --graph-enable)")
    ap.add_argument("--ner-prompt-file", help="read the triple-extraction prompt from a file")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the knowledge_base_id on success")
    args = ap.parse_args(argv)

    if not args.api_key:
        print("missing API key (--api-key or GPTBOTS_API_KEY)", file=sys.stderr)
        return 4
    if not args.name.strip() or not args.desc.strip():
        print("--name and --desc must be non-empty", file=sys.stderr)
        return 4

    ner_prompt = args.ner_prompt
    if args.ner_prompt_file:
        p = Path(args.ner_prompt_file)
        if not p.is_file():
            print(f"ner prompt file not found: {p}", file=sys.stderr)
            return 4
        ner_prompt = p.read_text(encoding="utf-8")
    if ner_prompt and not args.graph_enable:
        print("warning: --ner-prompt is ignored unless --graph-enable is set", file=sys.stderr)

    payload = {
        "name": args.name,
        "desc": args.desc,
        "graph_enable": bool(args.graph_enable),
        "access_control_enabled": bool(args.access_control),
    }
    if args.graph_enable and ner_prompt:
        payload["kg_ner_extraction_user_prompt"] = ner_prompt

    resp = _post_json(f"{_base(args.endpoint)}/v1/bot/knowledge/base/create", args.api_key, payload)
    err = _explain(resp)
    if err:
        print(f"create failed: {err}", file=sys.stderr)
        return 3

    kb_id = resp["knowledge_base_id"]
    if args.quiet:
        print(kb_id)
    else:
        print(f"created knowledge base: name={args.name!r} knowledge_base_id={kb_id}")
        print("next: populate it via /v1/bot/doc/text/add | /v1/bot/doc/qa/add | "
              "/v1/bot/doc/spreadsheet/add (see references/call-gptbots-api.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
