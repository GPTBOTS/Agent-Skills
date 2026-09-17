#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-PRIVATE Skills for an existing GPTBots LoopAgent: create one from a .skill/.zip
package, or push a new package into one you created earlier -- via that Agent's OWN API Key.

    Agent API Key     -> Authorization: Bearer <key>          <- THIS SCRIPT (+ publish_gptbots.py)
    DevKey/DevSecret  -> Authorization: Basic base64(...)     <- gptbots_org_api.py (ORG-level Skills)

Endpoints (Agent API, multipart/form-data):
  create <pkg> [--category ID]            POST /v1/agent/skill/create   -> {skill_id, name, version}
  update <pkg> --skill-id ID [--category] POST /v1/agent/skill/update   -> {skill_id, name, version}

THE GATE (same as publish_gptbots.py): the key must be the target LoopAgent's API Key
**with version-management permission** -- a console-only grant (gptbots.ai -> the Agent ->
Integration / API -> create an API Key with version management enabled). A chat-only key,
or the key auto-created by the org import API, answers 403.

Scope and limits (from the API reference):
  - LoopAgent only. Plain Agents, FlowAgents and Workflows have no private Skills.
  - The Skill belongs to the Agent behind the key; `update` refuses a skill_id owned by
    another Agent (lookup is skill_id + project + bot).
  - Package: .skill or .zip, <= 20 MiB; <= 200 files; <= 5 MiB per file and <= 64 MiB in
    total once unpacked; SKILL.md at the root or inside the single top-level folder, with
    `name` in its frontmatter.
  - `update` is idempotent: an identical package returns the current version unchanged.
  - NEITHER CALL MOUNTS THE SKILL OR TOUCHES THE AGENT'S VERSIONS. Creating/updating only
    stores the Skill (and bumps its own version). To make the Agent use it, reference the
    returned skill_id in the ClawSkill satellite's `skillRefs[]` of the .bot and import
    that as a new Agent version (publish_gptbots.py), then release when the user says so.
    An already-mounted Skill picks up an `update` on its next run without a new Agent
    version -- the mount is by id, the content is versioned separately.

Usage:
  python3 gptbots_agent_skill.py create refund-policy.skill --api-key KEY [--endpoint sg]
  python3 gptbots_agent_skill.py update refund-policy-v2.skill --skill-id skill-xxxx --api-key KEY
  GPTBOTS_API_KEY=KEY python3 gptbots_agent_skill.py create refund-policy.skill --category cat-xxxx

Exit codes: 0 ok; 2 package failed the offline check; 3 API error; 4 usage error.
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

PERMISSION_HINT = (
    "this API Key has no version-management permission, or is not a LoopAgent's key -- "
    "create one on gptbots.ai (the LoopAgent -> Integration/API -> new API Key with version "
    "management enabled)"
)
STATUS_HINTS = {
    400: "bad parameters (package rejected? see the offline check output above)",
    401: "unauthorized -- check the API Key and the 'Bearer ' prefix",
    403: "forbidden -- " + PERMISSION_HINT,
    429: "rate limited",
    500: "server error",
}

PKG_MAX_BYTES = 20 * 1024 * 1024
PKG_MAX_FILES = 200
PKG_MAX_FILE_UNPACKED = 5 * 1024 * 1024
PKG_MAX_TOTAL_UNPACKED = 64 * 1024 * 1024


# ---------------------------------------------------------------- offline package check
def check_package(path):
    """Mirror the server-side package rules locally; return a list of problems."""
    pth = Path(path)
    problems = []
    if pth.suffix.lower() not in (".skill", ".zip"):
        problems.append("extension must be .skill or .zip (got %r)" % pth.suffix)
    if pth.stat().st_size > PKG_MAX_BYTES:
        problems.append("package is %.1f MiB; the limit is 20 MiB" % (pth.stat().st_size / 2**20))
    if not zipfile.is_zipfile(pth):
        problems.append("not a zip archive (a .skill is a zip with SKILL.md inside)")
        return problems
    with zipfile.ZipFile(pth) as z:
        infos = [i for i in z.infolist() if not i.filename.endswith("/")]
        names = [i.filename for i in infos]
        if len(infos) > PKG_MAX_FILES:
            problems.append("%d files in the package; the limit is %d" % (len(infos), PKG_MAX_FILES))
        big = [i.filename for i in infos if i.file_size > PKG_MAX_FILE_UNPACKED]
        if big:
            problems.append("files over 5 MiB unpacked: %s" % ", ".join(big[:5]))
        total = sum(i.file_size for i in infos)
        if total > PKG_MAX_TOTAL_UNPACKED:
            problems.append("unpacked size %.1f MiB exceeds 64 MiB" % (total / 2**20))
        tops = {n.split("/", 1)[0] for n in names}
        candidates = ["SKILL.md"]
        if len(tops) == 1:
            candidates.append("%s/SKILL.md" % next(iter(tops)))
        hit = next((c for c in candidates if c in names), None)
        if not hit:
            problems.append("no SKILL.md at the root or inside a single top-level folder "
                            "(top-level entries: %s)" % (", ".join(sorted(tops)) or "-"))
            return problems
        text = z.read(hit).decode("utf-8", "replace").lstrip("\ufeff")
        fm = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        if not fm:
            problems.append("%s has no YAML frontmatter (--- ... ---)" % hit)
        elif not re.search(r"^name\s*:\s*\S", fm.group(1), re.M):
            problems.append("%s frontmatter has no `name`" % hit)
    return problems


# ---------------------------------------------------------------- http plumbing
def _base(endpoint):
    return "https://api-%s.gptbots.ai" % endpoint


def _multipart(url, api_key, file_path, fields):
    boundary = "----gptbots" + uuid.uuid4().hex
    fname = Path(file_path).name
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, key, value)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (boundary, fname, ctype)).encode())
    parts.append(Path(file_path).read_bytes())
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or ""
        try:
            data = json.loads(raw)
        except Exception:
            data = {"code": e.code, "message": raw[:300] or str(e)}
        data.setdefault("http_status", e.code)
        if e.code in STATUS_HINTS and not data.get("hint"):
            data["hint"] = STATUS_HINTS[e.code]
        return data
    except urllib.error.URLError as e:
        raise SystemExit("network error: %s" % e)


def _fail(r):
    if r.get("code", 0) != 0 or "http_status" in r:
        msg = "%s (code %s)" % (r.get("message"), r.get("code"))
        if r.get("hint"):
            msg += " -- " + r["hint"]
        return msg
    return None


# ---------------------------------------------------------------- commands
def _gate(pkg):
    problems = check_package(pkg)
    if problems:
        print("package rejected before upload:", file=sys.stderr)
        for pr in problems:
            print("  - " + pr, file=sys.stderr)
    return not problems


def cmd_create(a):
    if not _gate(a.package):
        return 2
    r = _multipart(_base(a.endpoint) + "/v1/agent/skill/create", a.api_key, a.package,
                   {"category_id": a.category})
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    err = _fail(r)
    if err:
        print("create private skill failed: %s" % err, file=sys.stderr); return 3
    d = r.get("data") or {}
    print("private skill created: skill_id=%s name=%s version=%s"
          % (d.get("skill_id"), d.get("name"), d.get("version")))
    print("  NOT mounted yet: add {\"skillId\": \"%s\", \"enabled\": true, \"source\": "
          "\"ORGANIZATION\"} to the ClawSkill satellite's skillRefs[] in the .bot, import it as "
          "a new version with publish_gptbots.py, and release on the user's go-ahead."
          % d.get("skill_id"))
    print("  keep skill_id -- `update <pkg> --skill-id %s` pushes the next package version."
          % d.get("skill_id"))
    return 0


def cmd_update(a):
    if not _gate(a.package):
        return 2
    r = _multipart(_base(a.endpoint) + "/v1/agent/skill/update", a.api_key, a.package,
                   {"skill_id": a.skill_id, "category_id": a.category})
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    err = _fail(r)
    if err:
        print("update private skill failed: %s" % err, file=sys.stderr)
        print("  (the skill_id must belong to the Agent behind this key; an ORG-level Skill "
              "is updated with DevKey auth via gptbots_org_api.py update-skill)", file=sys.stderr)
        return 3
    d = r.get("data") or {}
    print("private skill updated: skill_id=%s name=%s version=%s"
          % (d.get("skill_id"), d.get("name"), d.get("version")))
    print("  (an identical package returns the current version unchanged; no Agent version "
          "was saved or released)")
    return 0


# ---------------------------------------------------------------- cli
def build_parser():
    common = argparse.ArgumentParser(add_help=False)   # accepted before or after the command
    common.add_argument("--api-key", default=os.environ.get("GPTBOTS_API_KEY"),
                        help="the LoopAgent's API Key with version-management permission "
                             "(or env GPTBOTS_API_KEY)")
    common.add_argument("--endpoint", default="sg", choices=["sg", "jp", "th"])
    common.add_argument("--json", action="store_true", help="print the raw response body")
    ap = argparse.ArgumentParser(
        description="Create / update an Agent-private Skill on a GPTBots LoopAgent (Agent API Key)",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__, parents=[common])
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("create", help="create a private Skill from a .skill/.zip package",
                       parents=[common])
    p.add_argument("package")
    p.add_argument("--category", help="category_id (omit -> uncategorised)")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("update", help="replace a private Skill's package (new Skill version)",
                       parents=[common])
    p.add_argument("package")
    p.add_argument("--skill-id", required=True, help="skill_id returned by create")
    p.add_argument("--category", help="new category_id (omit to keep the current one)")
    p.set_defaults(func=cmd_update)
    return ap


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not a.command:
        ap.print_help(); return 4
    if not a.api_key:
        print("missing API key: pass --api-key or set GPTBOTS_API_KEY "
              "(the LoopAgent's key with version-management permission).", file=sys.stderr)
        return 4
    if not Path(a.package).is_file():
        print("file not found: %s" % a.package, file=sys.stderr); return 4
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
