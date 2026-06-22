#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import a generated .bot / .flow into a **test-mode** GPTBots target and (optionally)
release that version live — the API path for "update & publish" without the console.

⚠️ Only a target created in **test mode** can be updated/published this way (the
mode is chosen at creation and is immutable). A non-test target returns 403200.

What it does, in order:
  1. (default) run validate_gptbots_config.py on the file — never import a config
     that fails the offline checks.
  2. POST the file to the import endpoint → the platform saves it as a new draft
     version (also the current version) and returns that version string.
  3. with --release, POST that version to the release endpoint → it goes live.

Endpoints (by file type):
  .bot   → /v1/agent/version/import       /v1/agent/version/release      (Agent Key)
  .flow  → /v1/workflow/version/import     /v1/workflow/version/release   (Workflow Key)
Base URL: https://api-{endpoint}.gptbots.ai  (endpoint: sg default / jp / th)

The API key is the TARGET's own key (Agent Key for .bot, Workflow Key for .flow),
from that target's Integration / API channel — it must match the endpoint or you
get 403204. Pass it via --api-key or the GPTBOTS_API_KEY env var; the key is never
written to disk or logged.

Usage:
  python3 publish_gptbots.py my-agent.bot  --api-key KEY [--endpoint sg]
  python3 publish_gptbots.py my-flow.flow  --api-key KEY --release --version-desc "v2"
  GPTBOTS_API_KEY=KEY python3 publish_gptbots.py my-agent.bot --release

Exit codes: 0 ok; 2 validation failed; 3 API error; 4 usage error.
"""
import argparse
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ERROR_CODES = {
    40348: "target does not exist",
    403200: "NOT in test mode — only test-mode targets can be updated/published via API",
    403201: "imported file type does not match the target type (.bot↔Agent, .flow↔Workflow)",
    403202: "the platform failed to parse the imported file",
    403203: "the specified version does not exist",
    403204: "API key type does not match this endpoint (Agent Key for .bot, Workflow Key for .flow)",
    40353: "published count exceeds the plan limit",
}


def _kind(path):
    suf = Path(path).suffix.lower()
    if suf == ".bot":
        return "agent"
    if suf == ".flow":
        return "workflow"
    raise SystemExit(f"unsupported file type {suf!r} — expected .bot or .flow")


def _base(endpoint):
    return f"https://api-{endpoint}.gptbots.ai"


def _post_multipart(url, api_key, file_path, version_desc):
    """POST a multipart/form-data body (file + optional versionDesc) with stdlib only."""
    boundary = "----gptbots" + uuid.uuid4().hex
    fname = Path(file_path).name
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    data = Path(file_path).read_bytes()
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                 f"filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
    parts.append(data)
    parts.append(b"\r\n")
    if version_desc:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"versionDesc\"\r\n\r\n{version_desc}\r\n".encode())
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    return _send(req)


def _post_json(url, api_key, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode() or "{}")
        except Exception:
            return {"code": e.code, "msg": str(e)}
    except urllib.error.URLError as e:
        raise SystemExit(f"network error: {e}")


def _explain(resp):
    code = resp.get("code")
    if code in (0, None) and resp.get("msg", "OK") == "OK":
        return None
    return f"code {code}: {ERROR_CODES.get(code, resp.get('msg', 'unknown error'))}"


def main(argv):
    ap = argparse.ArgumentParser(description="Import & optionally release a .bot/.flow to a test-mode GPTBots target")
    ap.add_argument("file", help="path to the .bot or .flow file")
    ap.add_argument("--api-key", default=os.environ.get("GPTBOTS_API_KEY"),
                    help="the TARGET's own Agent/Workflow key (or set GPTBOTS_API_KEY)")
    ap.add_argument("--endpoint", default="sg", choices=["sg", "jp", "th"], help="region (default sg)")
    ap.add_argument("--version-desc", default="Imported by AI tool", help="version note")
    ap.add_argument("--release", action="store_true", help="also publish the imported version live")
    ap.add_argument("--no-validate", action="store_true", help="skip the offline validator (not recommended)")
    args = ap.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr); return 4
    if not args.api_key:
        print("missing API key (--api-key or GPTBOTS_API_KEY)", file=sys.stderr); return 4
    kind = _kind(path)

    # 1) offline validation gate
    if not args.no_validate:
        validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
        if validator.exists():
            rc = subprocess.run([sys.executable, str(validator), str(path)]).returncode
            if rc != 0:
                print("validation failed — fix the config before importing", file=sys.stderr)
                return 2

    base = _base(args.endpoint)
    # 2) import
    imp = _post_multipart(f"{base}/v1/{kind}/version/import", args.api_key, str(path), args.version_desc)
    err = _explain(imp)
    if err:
        print(f"import failed: {err}", file=sys.stderr); return 3
    version = (imp.get("data") or {}).get("version")
    bot_id = (imp.get("data") or {}).get("botId")
    print(f"imported: target={bot_id} version={version}")

    # 3) optional release
    if args.release:
        if not version:
            print("no version returned to release", file=sys.stderr); return 3
        rel = _post_json(f"{base}/v1/{kind}/version/release", args.api_key, {"version": version})
        err = _explain(rel)
        if err:
            print(f"release failed: {err}", file=sys.stderr); return 3
        print(f"released live: version={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
