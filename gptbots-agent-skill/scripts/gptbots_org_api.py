#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account-level (DevKey/DevSecret) GPTBots API client — create & manage ORG resources.

This is the "create things on the platform" credential, distinct from an Agent/Workflow
API Key (Bearer) used for chat/runs and for that target's version endpoints:

    DevKey/DevSecret  -> Authorization: Basic base64(DevKey:DevSecret)   <- THIS SCRIPT
    Agent API Key     -> Authorization: Bearer <key>                     <- publish_gptbots.py

Get the pair at https://www.gptbots.ai/developer/profile (Profile -> Account -> Developer
info): the DevKey is copyable there and the API DevSecret can be revealed or reset.
Base64 is encoding, not encryption: never persist the token or the secret.

Commands:
  orgs                                   GET  /v1/org/list
  models                                 GET  /v1/model/list           (model VERSION ids)
  tools                                  GET  /v1/org/tool/list        (TOOL and/or MCP)
  skills                                 GET  /v1/org/skill/list
  create-tool                            POST /v1/org/tool/create
  update-tool                            PUT  /v1/org/tool/update
  delete-tool                            POST /v1/org/tool/delete
  create-mcp                             POST /v1/org/mcp/create
  refresh-mcp                            POST /v1/org/mcp/refresh
  delete-mcp                             POST /v1/org/mcp/delete
  create-skill                           POST /v1/org/skill/create
  import-skill <pkg>                     POST /v1/org/skill/import      (.zip/.skill)
  import-skill-url <url>                 POST /v1/org/skill/import/url
  delete-skill                           POST /v1/org/skill/delete
  precheck-agent <file.bot>              POST /v1/org/agent/import/precheck
  import-agent <file.bot>                POST /v1/org/agent/import      (creates an Agent)
  precheck-workflow <file.flow>          POST /v1/org/workflow/import/precheck
  import-workflow <file.flow>            POST /v1/org/workflow/import   (creates a Workflow)

Credentials:  --dev-key/--dev-secret, or env GPTBOTS_DEV_KEY / GPTBOTS_DEV_SECRET.
Region:       --endpoint sg|jp|th (default sg).

Examples:
  python3 gptbots_org_api.py orgs
  python3 gptbots_org_api.py models --org p-xxxx --agent-type LOOP_AGENT
  python3 gptbots_org_api.py models --org p-xxxx --capability CHAT --grep claude
  python3 gptbots_org_api.py precheck-agent my.bot --org p-xxxx
  python3 gptbots_org_api.py import-agent  my.bot --org p-xxxx --name "Support Bot"
  python3 gptbots_org_api.py create-tool --org p-xxxx --name weather --desc "Weather" \
          --logo https://cdn/x.png --url https://api.example.com --schema-file openapi.json

Exit codes: 0 ok; 2 precheck/validation failed; 3 API error; 4 usage error.
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEV_PROFILE_URL = "https://www.gptbots.ai/developer/profile"   # where the user copies DevKey / API DevSecret

AGENT_TYPES = ["AGENT", "FLOW_AGENT", "LOOP_AGENT", "WORKFLOW"]
CAPABILITIES = ["CHAT", "EMBEDDING", "RERANK", "SPEECH2TEXT",
                "TEXT2SPEECH", "MODERATION", "ANONYMIZATION"]

STATUS_HINTS = {
    400: "bad parameters",
    401: "unauthorized — check DevKey/DevSecret and the 'Basic ' prefix",
    403: "insufficient permission for this org resource",
    429: "rate limited (model/list is 60 req/min per account)",
    500: "server error",
}


# ---------------------------------------------------------------- http plumbing
def _base(endpoint):
    return "https://api-%s.gptbots.ai" % endpoint


def _basic(dev_key, dev_secret):
    raw = ("%s:%s" % (dev_key, dev_secret)).encode()
    return "Basic " + base64.b64encode(raw).decode()


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() or ""
        try:
            data = json.loads(body)
        except Exception:
            data = {"code": e.code, "message": STATUS_HINTS.get(e.code, body[:200] or str(e))}
        data.setdefault("http_status", e.code)
        return data
    except urllib.error.URLError as e:
        raise SystemExit("network error: %s" % e)


def _get(url, auth, params=None):
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = "%s?%s" % (url, qs)
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", auth)
    return _send(req)


def _json_call(url, auth, payload, method="POST"):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method)
    req.add_header("Authorization", auth)
    req.add_header("Content-Type", "application/json")
    return _send(req)


def _multipart(url, auth, file_path, fields):
    boundary = "----gptbots" + uuid.uuid4().hex
    fname = Path(file_path).name
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    parts = [("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
              "Content-Type: %s\r\n\r\n" % (boundary, fname, ctype)).encode(),
             Path(file_path).read_bytes(), b"\r\n"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, key, value)).encode())
    parts.append(("--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(url, data=b"".join(parts), method="POST")
    req.add_header("Authorization", auth)
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    return _send(req)


def _fail(resp):
    """Return an error string, or None when the response is a success."""
    code = resp.get("code")
    status = resp.get("http_status")
    if status and status >= 400:
        return "HTTP %s — %s" % (status, resp.get("message") or STATUS_HINTS.get(status, ""))
    if code in (0, None):
        return None
    return "code %s: %s" % (code, resp.get("message") or resp.get("msg") or "unknown error")


def _out(resp, as_json=True):
    print(json.dumps(resp.get("data", resp), ensure_ascii=False, indent=2) if as_json else resp)


# ---------------------------------------------------------------- commands
def cmd_orgs(a, auth):
    r = _get(_base(a.endpoint) + "/v1/org/list", auth)
    err = _fail(r)
    if err:
        print("list organizations failed: %s" % err, file=sys.stderr); return 3
    rows = r.get("data") or []
    if a.json:
        _out(r); return 0
    if not rows:
        print("(no organizations returned)"); return 0
    print("%-28s %-40s %s" % ("ORG_ID", "NAME", "OWNER"))
    for o in rows:
        print("%-28s %-40s %s" % (o.get("org_id", ""), o.get("org_name", ""),
                                  "yes" if o.get("is_owner") else "no"))
    return 0


def cmd_models(a, auth):
    r = _get(_base(a.endpoint) + "/v1/model/list", auth,
             {"org_id": a.org, "agent_type": a.agent_type})
    err = _fail(r)
    if err:
        print("list models failed: %s" % err, file=sys.stderr); return 3
    if a.json:
        _out(r); return 0
    data = r.get("data") or {}
    rows = []
    for capability, vendors in data.items():
        if a.capability and capability != a.capability:
            continue
        for vendor, models in (vendors or {}).items():
            for m in models or []:
                rows.append((capability, vendor,
                             m.get("model_name") or "",
                             m.get("aiModelVersion") or "",
                             m.get("modelId") or "",
                             ",".join(m.get("capabilities") or [])))
    if a.grep:
        needle = a.grep.lower()
        rows = [x for x in rows if needle in " ".join(x).lower()]
    if not rows:
        print("(no models matched — capability keys present: %s)"
              % ", ".join(k for k in data) or "none")
        return 0
    print("%-13s %-20s %-26s %-26s %-26s %s"
          % ("CAPABILITY", "VENDOR", "MODEL", "VERSION_NAME", "MODEL_VERSION_ID", "CAPABILITIES"))
    for row in rows:
        print("%-13s %-20s %-26s %-26s %-26s %s" % row)
    print("\n# MODEL_VERSION_ID is the stable id to write into a config "
          "(chatModelVersionId / clawRule llm.model / LLM node model).")
    if a.agent_type == "LOOP_AGENT":
        print("# LoopAgent: these AMH-gateway ids are the ONLY valid ones for clawRule.")
    elif not a.agent_type:
        print("# Tip: pass --agent-type to filter to what the target type may bind "
              "(LoopAgent REQUIRES --agent-type LOOP_AGENT).")
    return 0


def cmd_tools(a, auth):
    r = _get(_base(a.endpoint) + "/v1/org/tool/list", auth,
             {"org_id": a.org, "keyword": a.grep, "plugin_type": a.type,
              "available": None if a.available is None else str(a.available).lower()})
    err = _fail(r)
    if err:
        print("list tools failed: %s" % err, file=sys.stderr); return 3
    if a.json:
        _out(r); return 0
    rows = r.get("data") or []
    if not rows:
        print("(no tools/MCPs)"); return 0
    print("%-28s %-8s %-24s %-8s %-8s %s"
          % ("RESOURCE_ID", "TYPE", "NAME", "AVAIL", "ACTIONS", "URL"))
    for t in rows:
        print("%-28s %-8s %-24s %-8s %-8s %s"
              % (t.get("resource_id", ""), t.get("plugin_type", ""), t.get("name", ""),
                 t.get("available"), t.get("action_count"), t.get("url", "")))
    return 0


def cmd_skills(a, auth):
    r = _get(_base(a.endpoint) + "/v1/org/skill/list", auth,
             {"org_id": a.org, "keyword": a.grep, "category_id": a.category,
              "owner_type": a.owner_type, "owner_agent_id": a.owner_agent,
              "enable": None if a.enable is None else str(a.enable).lower()})
    err = _fail(r)
    if err:
        print("list skills failed: %s" % err, file=sys.stderr); return 3
    if a.json:
        _out(r); return 0
    rows = r.get("data") or []
    if not rows:
        print("(no skills)"); return 0
    print("%-28s %-30s %-30s %-14s %s"
          % ("SKILL_ID", "NAME", "DISPLAY_NAME", "OWNER_TYPE", "ENABLED"))
    for s in rows:
        print("%-28s %-30s %-30s %-14s %s"
              % (s.get("id") or s.get("skill_id", ""), s.get("name", ""),
                 s.get("display_name", ""), s.get("owner_type", ""), s.get("enable")))
    return 0


def cmd_create_tool(a, auth):
    payload = {"org_id": a.org, "name": a.name, "description": a.desc, "logo": a.logo,
               "url": a.url, "show_request": not a.hide_request}
    if a.display_name:
        payload["display_name"] = a.display_name
    schema = _read_schema(a)
    if schema is not None:
        payload["api_schema"] = schema
    r = _json_call(_base(a.endpoint) + "/v1/org/tool/create", auth, payload)
    err = _fail(r)
    if err:
        print("create tool failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("tool created: tool_id=%s name=%s available=%s"
          % (d.get("tool_id"), d.get("name"), d.get("available")))
    if not d.get("available"):
        print("note: available=false — no actions were generated. Pass --schema-file with an "
              "OpenAPI 3 schema, or fill it in later with update-tool.", file=sys.stderr)
    return 0


def cmd_update_tool(a, auth):
    payload = {"org_id": a.org, "tool_id": a.tool_id, "name": a.name, "description": a.desc,
               "logo": a.logo, "url": a.url, "show_request": not a.hide_request}
    if a.display_name:
        payload["display_name"] = a.display_name
    schema = _read_schema(a)
    if schema is not None:
        payload["api_schema"] = schema
    for key in ("auth_provider", "auth_type", "auth_key", "auth_key_name", "auth_key_tip",
                "auth_secret", "auth_secret_name", "auth_secret_tip"):
        value = getattr(a, key, None)
        if value:
            payload[key] = value
    r = _json_call(_base(a.endpoint) + "/v1/org/tool/update", auth, payload, method="PUT")
    err = _fail(r)
    if err:
        print("update tool failed: %s" % err, file=sys.stderr); return 3
    print("tool updated: affect_count=%s" % r.get("affect_count"))
    return 0


def _read_schema(a):
    if getattr(a, "schema_file", None):
        text = Path(a.schema_file).read_text(encoding="utf-8")
        json.loads(text)                       # fail fast on malformed JSON
        return text
    return getattr(a, "schema", None)


def cmd_create_mcp(a, auth):
    payload = {"org_id": a.org, "name": a.name, "description": a.desc, "logo": a.logo,
               "url": a.url, "show_request": not a.hide_request,
               "mcp_transport_type": a.transport}
    if a.display_name:
        payload["display_name"] = a.display_name
    if a.header:
        payload["headers"] = [_kv(h) for h in a.header]
    if a.query:
        payload["queries"] = [_kv(q) for q in a.query]
    r = _json_call(_base(a.endpoint) + "/v1/org/mcp/create", auth, payload)
    err = _fail(r)
    if err:
        print("create mcp failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("mcp created: mcp_id=%s available=%s action_count=%s"
          % (d.get("mcp_id"), d.get("available"), d.get("action_count")))
    if not d.get("available"):
        print("note: available=false — the MCP handshake failed; check --url and --transport.",
              file=sys.stderr)
    return 0


def _kv(pair):
    if "=" not in pair:
        raise SystemExit("expected key=value, got %r" % pair)
    k, v = pair.split("=", 1)
    return {"key": k, "value": v}


def cmd_refresh_mcp(a, auth):
    r = _json_call(_base(a.endpoint) + "/v1/org/mcp/refresh", auth,
                   {"org_id": a.org, "id": a.id})
    err = _fail(r)
    if err:
        print("refresh mcp failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("mcp refreshed: mcp_id=%s action_count=%s available=%s"
          % (d.get("mcp_id"), d.get("action_count"), d.get("available")))
    return 0


def cmd_create_skill(a, auth):
    desc = {"en_US": a.desc_en}
    if a.desc_zh:
        desc["zh_CN"] = a.desc_zh
    payload = {"org_id": a.org, "name": a.name, "description": desc}
    if a.display_name:
        payload["display_name"] = a.display_name
    if a.owner_agent:
        payload["owner_agent_id"] = a.owner_agent
    r = _json_call(_base(a.endpoint) + "/v1/org/skill/create", auth, payload)
    err = _fail(r)
    if err:
        print("create skill failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("skill created: skill_id=%s name=%s owner_type=%s"
          % (d.get("skill_id"), d.get("name"), d.get("owner_type")))
    return 0


def cmd_import_skill(a, auth):
    r = _multipart(_base(a.endpoint) + "/v1/org/skill/import", auth, a.package,
                   {"org_id": a.org, "category_id": a.category})
    err = _fail(r)
    if err:
        print("import skill failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("skill imported: skill_id=%s name=%s owner_type=%s"
          % (d.get("skill_id"), d.get("name"), d.get("owner_type")))
    return 0


def cmd_import_skill_url(a, auth):
    payload = {"org_id": a.org, "package_url": a.url}
    if a.file_name:
        payload["file_name"] = a.file_name
    if a.category:
        payload["category_id"] = a.category
    r = _json_call(_base(a.endpoint) + "/v1/org/skill/import/url", auth, payload)
    err = _fail(r)
    if err:
        print("import skill from url failed: %s\n"
              "(the host must be on the server's skill-package allow-list)" % err,
              file=sys.stderr)
        return 3
    d = r.get("data") or {}
    print("skill imported: skill_id=%s name=%s" % (d.get("skill_id"), d.get("name")))
    return 0


def cmd_delete(a, auth):
    path, body = {
        "delete-tool": ("/v1/org/tool/delete", {"org_id": a.org, "id": a.id}),
        "delete-mcp": ("/v1/org/mcp/delete", {"org_id": a.org, "id": a.id}),
        "delete-skill": ("/v1/org/skill/delete", {"org_id": a.org, "skill_id": a.id}),
    }[a.command]
    if not a.yes:
        print("refusing to delete without --yes (this is irreversible; skill deletion also "
              "removes drafts, version snapshots and package files)", file=sys.stderr)
        return 4
    r = _json_call(_base(a.endpoint) + path, auth, body)
    err = _fail(r)
    if err:
        print("%s failed: %s" % (a.command, err), file=sys.stderr); return 3
    print("%s ok: affect_count=%s" % (a.command, r.get("affect_count")))
    return 0


def _precheck(a, auth, kind):
    path = "/v1/org/%s/import/precheck" % kind
    r = _multipart(_base(a.endpoint) + path, auth, a.file, {"org_id": a.org})
    err = _fail(r)
    if err:
        return None, "precheck failed: %s" % err
    d = r.get("data") or {}
    if not d.get("valid"):
        return d, "file is NOT importable: %s" % (d.get("error_message") or "no reason given")
    return d, None


def cmd_precheck(a, auth):
    kind = "agent" if a.command.endswith("agent") else "workflow"
    d, err = _precheck(a, auth, kind)
    if err:
        print(err, file=sys.stderr); return 2 if d is not None else 3
    print("valid: name=%s bot_type=%s export_type=%s format_version=%s"
          % (d.get("name"), d.get("bot_type"), d.get("export_type"), d.get("format_version")))
    return 0


def cmd_import_target(a, auth):
    kind = "agent" if a.command == "import-agent" else "workflow"
    if not a.no_precheck:
        d, err = _precheck(a, auth, kind)
        if err:
            print(err, file=sys.stderr)
            print("aborting import (use --no-precheck to skip this gate)", file=sys.stderr)
            return 2 if d is not None else 3
        print("precheck ok: %s (%s)" % (d.get("name"), d.get("bot_type")))
    fields = {"org_id": a.org, "custom_name": a.name,
              "enable_api": None if a.enable_api is None else str(a.enable_api).lower()}
    if kind == "agent" and getattr(a, "group", None):
        fields["group_id"] = a.group
    r = _multipart(_base(a.endpoint) + "/v1/org/%s/import" % kind, auth, a.file, fields)
    err = _fail(r)
    if err:
        print("import failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    target_id = d.get("agent_id") or d.get("workflow_id")
    print("%s created: id=%s name=%s bot_type=%s"
          % (kind, target_id, d.get("name"), d.get("bot_type", kind.upper())))
    print("api_key: %s" % d.get("api_key"))
    print("  ^ returned ONCE — give it to the user now; it is not retrievable later.")
    print("api_enabled=%s version_manage_enabled=%s"
          % (d.get("api_enabled"), d.get("version_manage_enabled")))
    if not d.get("api_enabled"):
        print("note: API is not enabled for this target (the plan may not include API).",
              file=sys.stderr)
    if not d.get("version_manage_enabled"):
        print("note: this key CANNOT publish. To release/roll back via API the user must "
              "create an API Key with version-management permission on gptbots.ai "
              "(target -> Integration/API).", file=sys.stderr)
    if d.get("warning"):
        print("warning from platform: %s" % d["warning"], file=sys.stderr)
    return 0


# ---------------------------------------------------------------- cli
def build_parser():
    ap = argparse.ArgumentParser(
        description="GPTBots account-level (DevKey/DevSecret) API client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--dev-key", default=os.environ.get("GPTBOTS_DEV_KEY"))
    ap.add_argument("--dev-secret", default=os.environ.get("GPTBOTS_DEV_SECRET"))
    ap.add_argument("--endpoint", default="sg", choices=["sg", "jp", "th"])
    ap.add_argument("--json", action="store_true", help="print the raw response body")
    sub = ap.add_subparsers(dest="command")

    def org_arg(p, required=True):
        p.add_argument("--org", required=required, help="org_id from `orgs`")

    p = sub.add_parser("orgs", help="list organizations"); p.set_defaults(func=cmd_orgs)

    p = sub.add_parser("models", help="list model VERSION ids")
    p.add_argument("--org", help="org_id (returns that org's usable models)")
    p.add_argument("--agent-type", choices=AGENT_TYPES,
                   help="filter to what this target type may bind (LoopAgent: LOOP_AGENT)")
    p.add_argument("--capability", choices=CAPABILITIES)
    p.add_argument("--grep", help="substring filter over the printed rows")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("tools", help="list Tools / MCPs"); org_arg(p)
    p.add_argument("--type", choices=["TOOL", "MCP"])
    p.add_argument("--available", type=lambda s: s.lower() == "true")
    p.add_argument("--grep", help="keyword")
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("skills", help="list Skills"); org_arg(p)
    p.add_argument("--grep", help="keyword")
    p.add_argument("--category")
    p.add_argument("--owner-type", help="e.g. ORGANIZATION")
    p.add_argument("--owner-agent")
    p.add_argument("--enable", type=lambda s: s.lower() == "true")
    p.set_defaults(func=cmd_skills)

    def tool_fields(p, creating):
        org_arg(p)
        if not creating:
            p.add_argument("--tool-id", required=True)
        p.add_argument("--name", required=True, help="<=20 chars")
        p.add_argument("--display-name", help="<=50 chars")
        p.add_argument("--desc", required=True, help="<=100 chars")
        p.add_argument("--logo", required=True, help="icon URL")
        p.add_argument("--url", required=True, help="public http/https base URL")
        p.add_argument("--hide-request", action="store_true",
                       help="do not show the request body during calls")
        p.add_argument("--schema-file", help="OpenAPI 3 JSON file (generates actions)")
        p.add_argument("--schema", help="OpenAPI 3 JSON as a string")

    p = sub.add_parser("create-tool", help="create a Tool"); tool_fields(p, True)
    p.set_defaults(func=cmd_create_tool)

    p = sub.add_parser("update-tool", help="update a Tool"); tool_fields(p, False)
    for opt in ("auth-provider", "auth-type", "auth-key", "auth-key-name", "auth-key-tip",
                "auth-secret", "auth-secret-name", "auth-secret-tip"):
        p.add_argument("--" + opt)
    p.set_defaults(func=cmd_update_tool)

    p = sub.add_parser("create-mcp", help="create an MCP"); org_arg(p)
    p.add_argument("--name", required=True, help="<=20 chars")
    p.add_argument("--display-name")
    p.add_argument("--desc", required=True, help="<=100 chars")
    p.add_argument("--logo", required=True)
    p.add_argument("--url", required=True, help="public MCP server URL")
    p.add_argument("--transport", required=True, choices=["SSE", "STREAMABLE_HTTP"])
    p.add_argument("--hide-request", action="store_true")
    p.add_argument("--header", action="append", metavar="K=V", help="repeatable, <=10")
    p.add_argument("--query", action="append", metavar="K=V", help="repeatable, <=30")
    p.set_defaults(func=cmd_create_mcp)

    p = sub.add_parser("refresh-mcp", help="re-pull an MCP's tools"); org_arg(p)
    p.add_argument("--id", required=True, help="mcp_id")
    p.set_defaults(func=cmd_refresh_mcp)

    p = sub.add_parser("create-skill", help="create an empty Skill"); org_arg(p)
    p.add_argument("--name", required=True, help="<=50 chars")
    p.add_argument("--display-name")
    p.add_argument("--desc-en", required=True, help="en_US description (required by the API)")
    p.add_argument("--desc-zh")
    p.add_argument("--owner-agent", help="create a PRIVATE skill on this Agent")
    p.set_defaults(func=cmd_create_skill)

    p = sub.add_parser("import-skill", help="import a .zip/.skill package"); org_arg(p)
    p.add_argument("package")
    p.add_argument("--category")
    p.set_defaults(func=cmd_import_skill)

    p = sub.add_parser("import-skill-url", help="import a package from a public URL")
    org_arg(p)
    p.add_argument("url")
    p.add_argument("--file-name")
    p.add_argument("--category")
    p.set_defaults(func=cmd_import_skill_url)

    for name in ("delete-tool", "delete-mcp", "delete-skill"):
        p = sub.add_parser(name, help="delete (irreversible)"); org_arg(p)
        p.add_argument("--id", required=True)
        p.add_argument("--yes", action="store_true", help="required confirmation")
        p.set_defaults(func=cmd_delete)

    for name in ("precheck-agent", "precheck-workflow"):
        p = sub.add_parser(name, help="parse+scan the file, write nothing"); org_arg(p)
        p.add_argument("file")
        p.set_defaults(func=cmd_precheck)

    for name, ext in (("import-agent", ".bot"), ("import-workflow", ".flow")):
        p = sub.add_parser(name, help="create a new target from a %s file" % ext)
        org_arg(p)
        p.add_argument("file")
        p.add_argument("--name", help="custom_name for the created target")
        p.add_argument("--enable-api", type=lambda s: s.lower() == "true", default=None)
        p.add_argument("--no-precheck", action="store_true")
        if name == "import-agent":
            p.add_argument("--group", help="group_id to join after import")
        p.set_defaults(func=cmd_import_target)

    return ap


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not a.command:
        ap.print_help(); return 4
    if not a.dev_key or not a.dev_secret:
        print("missing credentials: pass --dev-key/--dev-secret or set "
              "GPTBOTS_DEV_KEY / GPTBOTS_DEV_SECRET.\n"
              "Get them at %s "
              "(Profile -> Account -> Developer info: DevKey / API DevSecret)." % DEV_PROFILE_URL,
              file=sys.stderr)
        return 4
    for attr in ("file", "package"):
        path = getattr(a, attr, None)
        if path and not Path(path).is_file():
            print("file not found: %s" % path, file=sys.stderr); return 4
    return a.func(a, _basic(a.dev_key, a.dev_secret))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
