#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version management for an EXISTING GPTBots Agent / Workflow: import a .bot/.flow as a new
version, publish it live, list the version history, and roll back — all via that target's
own API Key.

⚠️ THE GATE: these endpoints only work with an API Key that has **version-management
permission**, which can only be granted in the console:

    gptbots.ai -> the target -> Integration / API -> create an API Key with the
    version-management permission enabled.

A key auto-created by the org import API comes back with version_manage_enabled=false, and
an ordinary chat key has no management permission either — both answer HTTP 403 here. The
config is not the problem when that happens; the key is.

Creating a NEW Agent/Workflow from a file is a different credential and endpoint family
(account-level DevKey/DevSecret) — use gptbots_org_api.py for that.

What this does, in order:
  1. (default) run validate_gptbots_config.py on the file — never import a config that
     fails the offline checks.
  2. POST the file to the import endpoint -> the platform replaces the target's current
     configuration, saves it as a new version (which becomes current) and returns it.
  3. with --release, POST that version to the release endpoint -> it goes live.

Endpoints (by file type / --kind):
  .bot   -> /v1/agent/version/{import,release,list,rollback}      (Agent Key)
  .flow  -> /v1/workflow/version/{import,release,list,rollback}   (Workflow Key)
Base URL: https://api-{endpoint}.gptbots.ai  (endpoint: sg default / jp / th)

The API key is the TARGET's own key and must match the endpoint family or you get 403204.
Pass it via --api-key or GPTBOTS_API_KEY; it is never written to disk or logged.

Usage:
  python3 publish_gptbots.py my-agent.bot  --api-key KEY [--endpoint sg]
  python3 publish_gptbots.py my-flow.flow  --api-key KEY --release --version-desc "v2"
  python3 publish_gptbots.py --list-versions --kind agent --api-key KEY
  python3 publish_gptbots.py --rollback v1 --kind agent --release --api-key KEY
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

PERMISSION_HINT = (
    "this API Key has no version-management permission — create one on gptbots.ai "
    "(target -> Integration/API -> new API Key with version management enabled)"
)

ERROR_CODES = {
    403: "insufficient permission — " + PERMISSION_HINT,
    40348: "target does not exist",
    403200: "target does not accept API updates in its current mode (legacy gate)",
    403201: "imported file type does not match the target type (.bot↔Agent, .flow↔Workflow)",
    403202: "the platform failed to parse the imported file",
    403203: "the specified version does not exist — run --list-versions first",
    403204: "API key type does not match this endpoint (Agent Key for .bot, Workflow Key for .flow)",
    40353: "published count exceeds the plan limit",
}


def _kind_from_path(path):
    suf = Path(path).suffix.lower()
    if suf == ".bot":
        return "agent"
    if suf == ".flow":
        return "workflow"
    raise SystemExit("unsupported file type %r — expected .bot or .flow" % suf)


def _base(endpoint):
    return "https://api-%s.gptbots.ai" % endpoint


def _post_multipart(url, api_key, file_path, version_desc):
    """POST a multipart/form-data body (file + optional versionDesc) with stdlib only."""
    boundary = "----gptbots" + uuid.uuid4().hex
    fname = Path(file_path).name
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    data = Path(file_path).read_bytes()
    parts = []
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                  "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (boundary, fname, ctype)).encode())
    parts.append(data)
    parts.append(b"\r\n")
    if version_desc:
        parts.append(("--%s\r\nContent-Disposition: form-data; "
                      "name=\"versionDesc\"\r\n\r\n%s\r\n" % (boundary, version_desc)).encode())
    parts.append(("--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(url, data=b"".join(parts), method="POST")
    req.add_header("Authorization", "Bearer %s" % api_key)
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    return _send(req)


def _post_json(url, api_key, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", "Bearer %s" % api_key)
    req.add_header("Content-Type", "application/json")
    return _send(req)


def _get(url, api_key):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer %s" % api_key)
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            resp = json.loads(e.read().decode() or "{}")
        except Exception:
            resp = {"code": e.code, "msg": str(e)}
        resp.setdefault("http_status", e.code)
        return resp
    except urllib.error.URLError as e:
        raise SystemExit("network error: %s" % e)


def _explain(resp):
    """Return an error string, or None when the response is a success."""
    status = resp.get("http_status")
    if status == 403:
        return "HTTP 403: " + ERROR_CODES[403]
    code = resp.get("code")
    if status and status >= 400 and code in (0, None):
        return "HTTP %s: %s" % (status, resp.get("message") or resp.get("msg") or "request failed")
    if code in (0, None) and resp.get("msg", "OK") in ("OK", None):
        return None
    if code in (0, None):
        return None
    return "code %s: %s" % (code, ERROR_CODES.get(code) or resp.get("message")
                            or resp.get("msg") or "unknown error")


def _ms(value):
    if not value:
        return "-"
    import datetime
    return datetime.datetime.utcfromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M")


def do_list(base, kind, api_key, as_json=False):
    resp = _get("%s/v1/%s/version/list" % (base, kind), api_key)
    err = _explain(resp)
    if err:
        print("list versions failed: %s" % err, file=sys.stderr); return 3
    rows = resp.get("data") or []
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return 0
    if not rows:
        print("(no versions yet)"); return 0
    print("%-14s %-12s %-17s %-17s %-26s %s"
          % ("VERSION", "STATUS", "CREATED(UTC)", "RELEASED(UTC)", "CREATOR", "DESC"))
    for v in rows:
        print("%-14s %-12s %-17s %-17s %-26s %s"
              % (v.get("version", ""), v.get("version_status", ""),
                 _ms(v.get("create_time")), _ms(v.get("release_time")),
                 v.get("creator_email", ""), (v.get("version_desc") or "")[:60]))
    return 0


def do_release(base, kind, api_key, version):
    resp = _post_json("%s/v1/%s/version/release" % (base, kind), api_key, {"version": version})
    err = _explain(resp)
    if err:
        print("release failed: %s" % err, file=sys.stderr); return 3
    data = resp.get("data") or {}
    print("released live: version=%s (previous=%s)"
          % (data.get("version", version), data.get("previous_version") or "none"))
    return 0


def do_rollback(base, kind, api_key, args):
    payload = {"version": args.rollback}
    if args.new_version:
        payload["new_version"] = args.new_version
    if args.version_desc:
        payload["version_desc"] = args.version_desc
    payload["release"] = bool(args.release)
    resp = _post_json("%s/v1/%s/version/rollback" % (base, kind), api_key, payload)
    err = _explain(resp)
    if err:
        print("rollback failed: %s" % err, file=sys.stderr); return 3
    data = resp.get("data") or {}
    print("rolled back: source=%s -> new_version=%s created=%s released=%s"
          % (data.get("source_version", args.rollback), data.get("new_version"),
             data.get("created"), data.get("released")))
    for w in data.get("warnings") or []:
        print("warning: %s" % w, file=sys.stderr)
    if not args.release:
        print("note: saved as a new version but NOT published — rerun with --release, or "
              "publish it in the console, once reviewed.")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(
        description="Import / publish / list / roll back versions of an existing GPTBots "
                    "Agent or Workflow (requires an API Key with version-management permission)")
    ap.add_argument("file", nargs="?", help="path to the .bot or .flow file (import mode)")
    ap.add_argument("--api-key", default=os.environ.get("GPTBOTS_API_KEY"),
                    help="the TARGET's own Agent/Workflow key (or set GPTBOTS_API_KEY)")
    ap.add_argument("--endpoint", default="sg", choices=["sg", "jp", "th"], help="region (default sg)")
    ap.add_argument("--kind", choices=["agent", "workflow"],
                    help="target type — inferred from the file extension in import mode, "
                         "required for --list-versions / --rollback")
    ap.add_argument("--version-desc", default="Imported by AI tool", help="version note")
    ap.add_argument("--release", action="store_true",
                    help="publish the resulting version live (side-effectful)")
    ap.add_argument("--list-versions", action="store_true", help="print the version history and exit")
    ap.add_argument("--rollback", metavar="VERSION",
                    help="copy this earlier version into a NEW version (add --release to publish it)")
    ap.add_argument("--new-version", help="explicit version number for a rollback (default: auto)")
    ap.add_argument("--json", action="store_true", help="raw JSON for --list-versions")
    ap.add_argument("--no-validate", action="store_true", help="skip the offline validator (not recommended)")
    args = ap.parse_args(argv)

    if not args.api_key:
        print("missing API key (--api-key or GPTBOTS_API_KEY)", file=sys.stderr); return 4

    modes = [bool(args.file), args.list_versions, bool(args.rollback)]
    if sum(modes) != 1:
        print("pick exactly one mode: a file to import, --list-versions, or --rollback VERSION",
              file=sys.stderr)
        return 4

    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print("file not found: %s" % path, file=sys.stderr); return 4
        kind = args.kind or _kind_from_path(path)
    else:
        kind = args.kind
        if not kind:
            print("--kind agent|workflow is required for --list-versions / --rollback",
                  file=sys.stderr)
            return 4

    base = _base(args.endpoint)

    if args.list_versions:
        return do_list(base, kind, args.api_key, args.json)
    if args.rollback:
        return do_rollback(base, kind, args.api_key, args)

    # ---- import mode -------------------------------------------------------
    if not args.no_validate:
        validator = Path(__file__).resolve().parent / "validate_gptbots_config.py"
        if validator.exists():
            rc = subprocess.run([sys.executable, str(validator), str(path)]).returncode
            if rc != 0:
                print("validation failed — fix the config before importing", file=sys.stderr)
                return 2

    imp = _post_multipart("%s/v1/%s/version/import" % (base, kind),
                          args.api_key, str(path), args.version_desc)
    err = _explain(imp)
    if err:
        print("import failed: %s" % err, file=sys.stderr); return 3
    data = imp.get("data") or {}
    version = data.get("version")
    bot_id = data.get("botId") or data.get("bot_id")
    print("imported: target=%s version=%s" % (bot_id, version))
    if data.get("warning"):
        print("warning from platform: %s" % data["warning"], file=sys.stderr)

    if args.release:
        if not version:
            print("no version returned to release", file=sys.stderr); return 3
        return do_release(base, kind, args.api_key, version)
    print("not published — the version is saved as current/draft for review. "
          "Rerun with --release to go live.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
