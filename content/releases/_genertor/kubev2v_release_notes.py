#!/usr/bin/env python3
"""
Generate release notes for kubev2v Migration Planner repos by comparing a target
git tag to the previous tag using the GitHub REST API.

Usage:
  # Single tag for all repos (tries 0.11.0 and v0.11.0 per repo):
  python3 kubev2v_release_notes.py --tag 0.11.0

  # Latest tag per repository (from GitHub tag list + semver ordering):
  python3 kubev2v_release_notes.py --latest

  # Explicit base ref for all repos:
  python3 kubev2v_release_notes.py --tag 0.11.0 --from-tag 0.10.0

  # JSON on stdout (object with release_overview + repositories; or -o file.json):
  python3 kubev2v_release_notes.py --tag 0.11.0 --json

  # Custom markdown path (default without -o is release-notes-<tag>.md, e.g. release-notes-0.11.0.md):
  python3 kubev2v_release_notes.py --tag 0.11.0 -o notes/custom.md

Markdown defaults to `release-notes-<tag>.md` in the current directory (sanitized for the
filesystem; falls back to `release-notes.md` if no tag can be resolved). The H1 includes the
same tag (`--tag` value, or migration-planner’s resolved head tag when using `--latest`). The
Markdown begins with YAML frontmatter (`title`, `linkTitle`, `weight`) for static-site use
(e.g. Hugo); titles are `release notes v<version>` when a tag is known.

For kubev2v/assisted-migration-agent, commits are compared using the migration-planner
repository's agent-v2 submodule pointer (at the same planner base/head tags as this run),
so the agent section matches the agent revision bundled in the planner, not the agent
repo's own release tags. If the submodule is missing or the compare fails, the script
falls back to tag-compare in assisted-migration-agent. When both repos are included,
migration-planner is always processed first (order is adjusted automatically).

Optional: set GITHUB_TOKEN in the environment for higher rate limits and private repos.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


REPOS: tuple[tuple[str, str], ...] = (
    ("kubev2v", "migration-planner"),
    ("kubev2v", "migration-planner-ui-app"),
    ("kubev2v", "assisted-migration-agent"),
    ("kubev2v", "migration-planner-agent-ui"),
)

API = "https://api.github.com"

# migration-planner git submodule at this path -> kubev2v/assisted-migration-agent
MIGRATION_PLANNER = ("kubev2v", "migration-planner")
AGENT_V2_PATH = "agent-v2"
ASSISTED_MIGRATION_AGENT = ("kubev2v", "assisted-migration-agent")


@dataclass
class RepoResult:
    owner: str
    repo: str
    base: str | None
    head: str | None
    html_url: str | None = None
    total_commits: int = 0
    commits: list[dict[str, Any]] = field(default_factory=list)
    merged_prs: list[int] = field(default_factory=list)
    summary: str | None = None
    # When set, assisted-migration-agent was compared by agent-v2 submodule SHAs in migration-planner.
    # Tuples: (planner_base_tag, planner_head_tag, old_submodule_commit_sha, new_submodule_commit_sha)
    agent_v2_submodule: tuple[str, str, str, str] | None = None
    error: str | None = None


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kubev2v-release-notes-script",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _github_request_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def github_get(path: str, params: dict[str, str] | None = None) -> Any:
    url = f"{API}{path}"
    if params:
        q = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
        url = f"{url}?{q}"
    try:
        return _github_request_json(url)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {body}") from e


def github_get_404(path: str, params: dict[str, str] | None = None) -> Any | None:
    """GET; return None on 404 (for optional submodule or missing paths)."""
    url = f"{API}{path}"
    if params:
        q = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items())
        url = f"{url}?{q}"
    try:
        return _github_request_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url}: {body}") from e


def fetch_all_tags(owner: str, repo: str) -> list[str]:
    """Return all tag names (paginated)."""
    names: list[str] = []
    page = 1
    per_page = 100
    while True:
        data = github_get(
            f"/repos/{owner}/{repo}/tags",
            {"per_page": str(per_page), "page": str(page)},
        )
        if not isinstance(data, list) or not data:
            break
        for item in data:
            if isinstance(item, dict) and "name" in item:
                names.append(str(item["name"]))
        if len(data) < per_page:
            break
        page += 1
    return names


def version_key(name: str) -> tuple:
    """
    Best-effort sort key for tags like 0.11.0, v0.11.0, 0.1.4-1, v0.0.38.
    Unknown shapes sort last.
    """
    raw = name.strip()
    if raw.startswith("v") or raw.startswith("V"):
        raw = raw[1:]
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", raw)
    if m:
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
        suffix = m.group(4) or ""
        return (0, major, minor, patch, suffix)
    m = re.match(r"^(\d+)$", raw)
    if m:
        return (0, int(m.group(1)), 0, 0, "")
    return (1, name)


def normalize_tag_input(tag: str) -> set[str]:
    """Possible ref names to try on GitHub."""
    t = tag.strip()
    s = {t, f"v{t}"}
    if t.startswith("v") or t.startswith("V"):
        s.add(t[1:])
    return s


def resolve_existing_tag(all_tags: list[str], wanted: str) -> str | None:
    candidates = normalize_tag_input(wanted)
    for n in all_tags:
        if n in candidates:
            return n
        if n.lstrip("vV") in {c.lstrip("vV") for c in candidates}:
            return n
    return None


def previous_tag(sorted_tags: list[str], head: str) -> str | None:
    """sorted_tags: ascending by version_key."""
    try:
        idx = sorted_tags.index(head)
    except ValueError:
        return None
    if idx <= 0:
        return None
    return sorted_tags[idx - 1]


def compare_commits(owner: str, repo: str, base: str, head: str) -> dict[str, Any]:
    # base...head : commits reachable from head not in base (GitHub single path segment).
    basehead = f"{base}...{head}"
    path = f"/repos/{owner}/{repo}/compare/{urllib.parse.quote(basehead, safe='/:.+_-+')}"
    return github_get(path)


def fetch_submodule_commit_at_ref(owner: str, repo: str, path: str, ref: str) -> str | None:
    """
    Return the commit SHA the submodule points to at the given ref (tag/branch), or None.
    See: GET /repos/{owner}/{repo}/contents/{path}?ref=...
    """
    p = f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}"
    data = github_get_404(p, {"ref": ref})
    if not isinstance(data, dict):
        return None
    if data.get("type") == "submodule" and data.get("sha"):
        return str(data["sha"])
    return None


def apply_compare_to_repo_result(rr: RepoResult, owner: str, repo: str, data: dict[str, Any]) -> None:
    """Fill compare-derived fields on rr (commits, PR ids, summary)."""
    if not isinstance(data, dict):
        rr.error = "unexpected compare response"
        return
    prs: set[int] = set()
    out_commits: list[dict[str, Any]] = []
    rr.total_commits = int(data.get("total_commits") or 0)
    commits = data.get("commits") or []
    if isinstance(commits, list):
        for c in commits:
            if not isinstance(c, dict):
                continue
            commit = c.get("commit") or {}
            msg = (commit.get("message") or "").split("\n", 1)[0].strip()
            author = (commit.get("author") or {}).get("name") or ""
            pm = pr_from_merge_commit(commit.get("message") or "")
            if pm:
                prs.add(pm)
            else:
                for n in extract_pr_numbers(commit.get("message") or ""):
                    prs.add(n)
            sha = c.get("sha", "")[:7]
            out_commits.append(
                {
                    "sha": sha,
                    "message": msg,
                    "author": author,
                }
            )
    rr.commits = out_commits
    rr.merged_prs = sorted(prs)
    rr.summary = build_two_sentence_summary([c["message"] for c in out_commits])


def extract_pr_numbers(commit_message: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"#(\d+)", commit_message)]


def pr_from_merge_commit(message: str) -> int | None:
    m = re.search(r"Merge pull request #(\d+)", message, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\(#(\d+)\)\s*$", message)
    if m:
        return int(m.group(1))
    return None


def is_module_update_message(message: str) -> bool:
    """Heuristic for Go modules, Renovate, Dependabot, npm/yarn lockfile bumps, etc."""
    m = message.strip()
    if not m:
        return False
    low = m.lower()
    if low.startswith("update module "):
        return True
    if low.startswith("bump "):
        return True
    if low.startswith("chore(deps)") or low.startswith("build(deps)"):
        return True
    if low.startswith("chore: bump") or low.startswith("chore: update"):
        return True
    if low.startswith("deps:") or low.startswith("[deps]"):
        return True
    if "renovate" in low[:50]:
        return True
    if "update dependency" in low or "update dependencies" in low:
        return True
    if "lock file" in low or "lockfile" in low:
        return True
    if "go.mod" in m or "go.sum" in m:
        return True
    if re.match(r"^fix\(deps\)", low):
        return True
    return False


def _is_bump_message(message: str) -> bool:
    """Dependency / version bumps (exclude from all summaries)."""
    m = message.strip()
    if not m:
        return False
    low = m.lower()
    if re.match(r"^\s*bump\b", low):
        return True
    if re.search(r"(?i)(^|[\s;])(chore|build|deps|ci)\b[^:]{0,40}:\s*bump\b", m):
        return True
    if re.search(r"(?i)\bbump\b.*\b(version|dependency|dependencies|package|image)\b", m):
        return True
    return False


def is_excluded_from_summary(message: str) -> bool:
    """Drop fixes, chores, docs, upgrades, tests, and merge noise from the auto-summary."""
    m = message.strip()
    if not m:
        return True
    if is_module_update_message(m):
        return True
    if _is_bump_message(m):
        return True
    low = m.lower()
    if re.match(r"^\s*fix\s*(\([^)]*\))?\s*!?\s*:", m, re.I):
        return True
    if re.search(r"(?i)(^|[\s;])(fix|fixes|hotfix|bugfix)\s*(\([^)]*\))?\s*!?\s*:", m):
        return True
    if low.startswith("merge pull request"):
        return True
    if low.startswith("revert"):
        return True
    if low.startswith("fix") or low.startswith("fixes"):
        return True
    if low.startswith("chore") or low.startswith("docs") or low.startswith("doc("):
        return True
    if low.startswith("doc:") or low.startswith("documentation"):
        return True
    if low.startswith("test(") or low.startswith("tests:") or low.startswith("test:"):
        return True
    if low.startswith("build(") or low.startswith("ci(") or low.startswith("ci:"):
        return True
    if low.startswith("style(") or low.startswith("lint(") or low.startswith("format"):
        return True
    if low.startswith("refactor("):
        return True
    if low.startswith("update module"):
        return True
    if "renovate" in low[:50]:
        return True
    if "upgrade" in low and ("depend" in low or "module" in low or "dep " in low):
        return True
    if "go.mod" in m or "go.sum" in m:
        return True
    if "readme" in low or "documentation" in low:
        return True
    if low.startswith("document") or low.startswith("doc "):
        return True
    return False


def _strip_conventional_subject(message: str) -> str:
    m = message.strip()
    m = re.sub(
        r"^(feat|feature|add)(\([^)]*\))?\s*:\s*",
        "",
        m,
        flags=re.I,
    )
    return m.strip() or message.strip()


_JIRA_TICKET = re.compile(
    r"\bECOPROJECT-\d+\b|"
    r"\b[A-Z][A-Z0-9_]{1,20}-\d{2,}\b",
    re.I,
)


def _strip_jira_meta_prefixes(text: str) -> str:
    """Remove NO-JIRA markers such as 'NO-JIRA |' from commit subjects."""
    s = text.strip()
    s = re.sub(r"(?i)^\s*NO-JIRA\s*\|\s*", "", s)
    s = re.sub(r"(?i)\s*\|\s*NO-JIRA\s*$", "", s)
    s = re.sub(r"(?i)\s*\|\s*NO-JIRA\s*\|\s*", " ", s)
    return s.strip()


def _strip_jira_tickets(text: str) -> str:
    """Remove Jira keys (e.g. ECOPROJECT-123, PROJECT-456) from summary fragments."""
    s = _JIRA_TICKET.sub("", text)
    s = re.sub(r"\s*[\[\(]\s*[\]\)]\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[\s\-–—:]+|[\s\-–—:]+$", "", s).strip()
    return s


def _clean_summary_fragment(raw: str) -> str:
    m = _strip_conventional_subject(raw)
    m = _strip_jira_meta_prefixes(m)
    m = _strip_jira_tickets(m)
    return html.escape(m)


def _truncate_words(s: str, max_len: int = 140) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _join_natural(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def build_two_sentence_summary(commit_messages: list[str]) -> str:
    """Heuristic 2-sentence blurb favoring feature-like subjects (not fixes/docs/deps)."""
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in commit_messages:
        if is_excluded_from_summary(raw):
            continue
        cleaned = _truncate_words(_clean_summary_fragment(raw))
        if len(cleaned) < 3:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    if not candidates:
        return (
            "This range does not show clear feature-style work in commit subjects alone. "
            "See dependency updates, the commit list, and merged PRs for fixes, upgrades, and docs."
        )

    if len(candidates) == 1:
        return (
            f"The main change described is: {_join_natural(candidates)}. "
            "Review the commits below for the full picture, including fixes and maintenance."
        )

    first_batch = candidates[:3]
    rest = candidates[3:6]
    s1 = f"This release emphasizes new and expanded behavior around {_join_natural(first_batch)}."
    if rest:
        s2 = f"Additional scope includes {_join_natural(rest)}."
    else:
        s2 = "Further detail is in the commit list below."
    return f"{s1} {s2}"


def is_feature_or_enhancement_for_global_overview(message: str) -> bool:
    """Stricter filter: new features or enhancements only (for cross-repo overview)."""
    if is_excluded_from_summary(message):
        return False
    low = message.strip().lower()
    if re.match(r"^\s*(feat|feature)\s*(\([^)]*\))?\s*!?\s*:", low):
        return True
    if re.search(r"(?i)\b(enhance|enhancement|extend(ing|ed)?|introduc(e|ing))\b", message):
        return True
    if re.search(
        r"(?i)\bimprove\s+(the\s+)?(ui|ux|workflow|flow|experience|performance|capacity|integration|api|migration|planner|agent|console)\b",
        message,
    ):
        return True
    if re.match(r"^\s*add\s+", low) and not re.match(
        r"^\s*add\s+(test|fixture|mock|stub|dependency|deps?|lint|ci)\b",
        low,
    ):
        return True
    return False


def build_global_release_overview(results: list[RepoResult]) -> str:
    """Two sentences across all repositories: features and enhancements only."""
    candidates: list[str] = []
    seen: set[str] = set()
    for rr in results:
        if rr.error:
            continue
        for cm in rr.commits:
            if not is_feature_or_enhancement_for_global_overview(cm["message"]):
                continue
            cleaned = _truncate_words(_clean_summary_fragment(cm["message"]))
            if len(cleaned) < 3:
                continue
            if cleaned not in seen:
                seen.add(cleaned)
                candidates.append(cleaned)

    if not candidates:
        return (
            "No feature or enhancement-style commits were identified across repositories in this range. "
            "See each repository section for other changes, including fixes and maintenance."
        )

    if len(candidates) == 1:
        return (
            f"Across the Migration Planner repositories, the main addition is {_join_natural(candidates)}. "
            "Per-repository sections below list the full change set."
        )

    first_batch = candidates[:4]
    rest = candidates[4:8]
    s1 = (
        "Across the Migration Planner repositories, new and enhanced capabilities include "
        f"{_join_natural(first_batch)}."
    )
    if rest:
        s2 = f"Further enhancements cover {_join_natural(rest)}."
    else:
        s2 = "Repository-specific summaries and commit lists provide additional detail."
    return f"{s1} {s2}"


def process_repo(
    owner: str,
    repo: str,
    head_wanted: str | None,
    use_latest: bool,
    from_tag: str | None,
    planner_tag_pair: tuple[str, str] | None = None,
) -> RepoResult:
    """
    For kubev2v/assisted-migration-agent, if planner_tag_pair is set (from migration-planner
    base/head tag resolution), diff the agent by the agent-v2 submodule commit range at those
    planner tags, instead of the agent repo's own tags.
    """
    po, pr = MIGRATION_PLANNER
    is_agent = (owner, repo) == ASSISTED_MIGRATION_AGENT

    if is_agent and planner_tag_pair is not None:
        pl_base, pl_head = planner_tag_pair
        old_sha = fetch_submodule_commit_at_ref(po, pr, AGENT_V2_PATH, pl_base)
        new_sha = fetch_submodule_commit_at_ref(po, pr, AGENT_V2_PATH, pl_head)
        if old_sha and new_sha:
            sub_rr = RepoResult(owner, repo, pl_base, pl_head)
            sub_rr.html_url = f"https://github.com/{owner}/{repo}"
            sub_rr.agent_v2_submodule = (pl_base, pl_head, old_sha, new_sha)
            if old_sha == new_sha:
                sub_rr.total_commits = 0
                sub_rr.commits = []
                sub_rr.merged_prs = []
                sub_rr.summary = build_two_sentence_summary([])
                return sub_rr
            try:
                data = compare_commits(owner, repo, old_sha, new_sha)
            except Exception:
                pass
            else:
                apply_compare_to_repo_result(sub_rr, owner, repo, data)
                if not sub_rr.error:
                    return sub_rr

    rr = RepoResult(owner=owner, repo=repo, base=None, head=None)
    try:
        tags = fetch_all_tags(owner, repo)
    except Exception as e:
        rr.error = str(e)
        return rr

    if not tags:
        rr.error = "no tags found"
        return rr

    ordered = sorted(set(tags), key=version_key)

    if use_latest:
        head = ordered[-1]
    else:
        assert head_wanted is not None
        head = resolve_existing_tag(tags, head_wanted)
        if not head:
            rr.error = f"tag {head_wanted!r} not found (try with or without v prefix)"
            return rr

    if from_tag:
        base = resolve_existing_tag(tags, from_tag)
        if not base:
            rr.error = f"--from-tag {from_tag!r} not found"
            return rr
    else:
        base = previous_tag(ordered, head)

    rr.head = head
    rr.base = base
    rr.html_url = f"https://github.com/{owner}/{repo}"

    if base is None:
        rr.error = "no earlier tag to compare (first tag or use --from-tag)"
        return rr

    try:
        data = compare_commits(owner, repo, base, head)
    except Exception as e:
        rr.error = str(e)
        return rr

    apply_compare_to_repo_result(rr, owner, repo, data)
    return rr


def resolve_title_tag(args: argparse.Namespace, results: list[RepoResult]) -> str | None:
    """Head tag string for the document title (--tag input, or planner head when --latest)."""
    if getattr(args, "tag", None):
        return str(args.tag).strip()
    if getattr(args, "latest", False):
        for rr in results:
            if (rr.owner, rr.repo) == MIGRATION_PLANNER and rr.head and not rr.error:
                return rr.head
        for rr in results:
            if rr.head and not rr.error:
                return rr.head
    return None


def sanitize_filename_tag(tag: str) -> str:
    """Make a tag safe as a single filename component (e.g. v0.11.0 → v0.11.0, a/b → a-b)."""
    s = tag.strip()
    if not s:
        return "release"
    out: list[str] = []
    for c in s:
        if c.isalnum() or c in "._-+":
            out.append(c)
        else:
            out.append("-")
    x = "".join(out)
    x = re.sub(r"-+", "-", x).strip("-")
    return x if x else "release"


def default_markdown_path(title_tag: str | None) -> str:
    """Default output path when `-o` is omitted."""
    if title_tag:
        return f"release-notes-{sanitize_filename_tag(title_tag)}.md"
    return "release-notes.md"


def version_doc_label(tag: str) -> str:
    """Display version like v0.11.0 (single leading v) for Hugo/docs frontmatter."""
    t = tag.strip()
    if not t:
        return ""
    if t.startswith("v") or t.startswith("V"):
        return "v" + t[1:]
    return "v" + t


def frontmatter_doc_title(title_tag: str | None) -> str:
    """title / linkTitle value: release notes v<target> or release notes when no tag."""
    if title_tag and str(title_tag).strip():
        return f"release notes {version_doc_label(str(title_tag).strip())}"
    return "release notes"


def yaml_single_quoted_scalar(s: str) -> str:
    """YAML single-quoted scalar (escape `'` → `''`)."""
    return "'" + s.replace("'", "''") + "'"


def render_markdown_frontmatter(title_tag: str | None) -> list[str]:
    """Hugo-compatible metadata (title, linkTitle, weight) above the Markdown body."""
    doc_title = frontmatter_doc_title(title_tag)
    title_q = yaml_single_quoted_scalar(doc_title)
    return [
        "---",
        f"title: {title_q}",
        f"linkTitle: {title_q}",
        "weight: 2",
        "---",
        "",
    ]


def render_markdown(results: list[RepoResult], title_tag: str | None = None) -> str:
    overview = build_global_release_overview(results)
    h1 = "# Migration Planner — combined release notes"
    if title_tag:
        h1 = f"{h1} — `{title_tag}`"
    lines = render_markdown_frontmatter(title_tag) + [
        h1,
        "",
        "## Release overview",
        "",
        overview,
        "",
        "Generated from GitHub compare (previous tag → target tag).",
        "",
    ]
    for rr in results:
        name = f"{rr.owner}/{rr.repo}"
        url = f"https://github.com/{rr.owner}/{rr.repo}"
        lines.append(f"## [{name}]({url})")
        lines.append("")
        if rr.error:
            lines.append(f"_Error: {html.escape(rr.error)}_")
            lines.append("")
            continue
        if rr.agent_v2_submodule:
            ptb, pth, osha, nsha = rr.agent_v2_submodule
            cmp_url = f"https://github.com/{rr.owner}/{rr.repo}/compare/{osha}...{nsha}"
            pl_url = "https://github.com/kubev2v/migration-planner"
            lines.append(
                f"- **Compare (assisted-migration-agent, via migration-planner `agent-v2` submodule):** "
                f"[`{osha[:7]}` → `{nsha[:7]}`]({cmp_url}) "
                f"([migration-planner]({pl_url}) tags `{ptb}` → `{pth}`)"
            )
        else:
            lines.append(f"- **Compare:** `{rr.base}` → `{rr.head}`")
        lines.append(f"- **Commits:** {rr.total_commits}")
        lines.append("")
        lines.append("### Summary")
        lines.append("")
        lines.append(rr.summary or "")
        lines.append("")
        if rr.merged_prs:
            pr_links = ", ".join(
                f"[#{n}](https://github.com/{rr.owner}/{rr.repo}/pull/{n})" for n in rr.merged_prs
            )
            lines.append(f"- **PRs referenced:** {pr_links}")
        lines.append("")
        if rr.commits:
            lines.append("### Commits")
            lines.append("")
            for cm in rr.commits:
                lines.append(f"- `{cm['sha']}` {html.escape(cm['message'])}")
            lines.append("")
        else:
            lines.append("_No commits in range (or compare empty)._")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Build release notes for kubev2v repos from git tags.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tag", help="Version tag, e.g. 0.11.0 (matches v0.11.0 when present)")
    g.add_argument("--latest", action="store_true", help="Use latest semver-like tag per repo")
    p.add_argument(
        "--from-tag",
        help="Explicit base tag for all repos (default: tag before --tag / --latest)",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    p.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Output file. Markdown default: release-notes-<tag>.md (or release-notes.md); "
        "with --json, writes JSON to PATH; if omitted, JSON goes to stdout.",
    )
    p.add_argument(
        "--repo",
        action="append",
        metavar="OWNER/NAME",
        help="Restrict to repo(s); can repeat. Default: all four kubev2v repos",
    )
    args = p.parse_args()

    repos = REPOS
    if args.repo:
        parsed: list[tuple[str, str]] = []
        for r in args.repo:
            if "/" not in r:
                print(f"invalid --repo {r!r}, want owner/name", file=sys.stderr)
                return 2
            o, n = r.split("/", 1)
            parsed.append((o, n))
        repos = tuple(parsed)

    repo_list = list(repos)
    if MIGRATION_PLANNER in repo_list and ASSISTED_MIGRATION_AGENT in repo_list:
        repo_list = [MIGRATION_PLANNER] + [r for r in repo_list if r != MIGRATION_PLANNER]
    repos = tuple(repo_list)

    results: list[RepoResult] = []
    planner_ref_pair: tuple[str, str] | None = None
    for owner, name in repos:
        pair = planner_ref_pair if (owner, name) == ASSISTED_MIGRATION_AGENT else None
        r = process_repo(
            owner,
            name,
            head_wanted=args.tag,
            use_latest=bool(args.latest),
            from_tag=args.from_tag,
            planner_tag_pair=pair,
        )
        if (owner, name) == MIGRATION_PLANNER and not r.error and r.base and r.head:
            planner_ref_pair = (r.base, r.head)
        results.append(r)

    title_tag = resolve_title_tag(args, results)

    if args.json:
        repos_out = []
        for rr in results:
            avs = None
            if rr.agent_v2_submodule:
                ptb, pth, oa, ob = rr.agent_v2_submodule
                avs = {
                    "planner_base_tag": ptb,
                    "planner_head_tag": pth,
                    "assisted_old_sha": oa,
                    "assisted_new_sha": ob,
                }
            repos_out.append(
                {
                    "owner": rr.owner,
                    "repo": rr.repo,
                    "base": rr.base,
                    "head": rr.head,
                    "html_url": rr.html_url,
                    "total_commits": rr.total_commits,
                    "commits": rr.commits,
                    "merged_prs": rr.merged_prs,
                    "summary": rr.summary,
                    "agent_v2_submodule": avs,
                    "error": rr.error,
                }
            )
        payload_obj = {
            "release_overview": build_global_release_overview(results),
            "repositories": repos_out,
        }
        payload = json.dumps(payload_obj, indent=2) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(payload)
            print(f"Wrote {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(payload)
    else:
        md_path = args.output if args.output is not None else default_markdown_path(title_tag)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_markdown(results, title_tag))
        print(f"Wrote {md_path}", file=sys.stderr)

    if any(r.error for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
