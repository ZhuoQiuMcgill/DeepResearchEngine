"""Bounded draft/review policy and deterministic citation checks."""
from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markdown_it.rules_inline import link

from deepresearch.engine.contracts import EngineError
from deepresearch.workflows.components.agents import invoke_role
from ..contracts import ReportReview
from .roles import decision, retain


def _reference_entries(references, known):
    """Read actual prose references, retaining raw, plain source-ID labels.

    Markdown handles destination/title syntax. URLs remain exact: no percent
    decoding, URL guessing or normalization; the existing whole-entry URL check
    additionally guards raw URL spellings. Continuation lines belong to the
    preceding entry only within the same parsed block and before the next label.
    Raw HTML paragraphs are unsupported.
    """
    parser = MarkdownIt("commonmark")
    parser.normalizeLink = lambda url: url
    label_pattern = re.compile(r"\[([A-Za-z0-9_.-]+)\]")

    def source_link(state, silent):
        start, count = state.pos, len(state.tokens)
        if not link(state, silent):
            return False
        label = label_pattern.match(state.src, start)
        if not silent and label and state.src[label.end():label.end() + 1] == "(":
            token = next(token for token in state.tokens[count:] if token.type == "link_open")
            token.meta["source_id"] = label[1]
            token.meta["reference_line"] = state.src[:start].count("\n")
        return True

    def source_label(state, silent):
        if silent:
            return False  # Leave bracket nesting to the unmodified Markdown parser.
        label = label_pattern.match(state.src, state.pos)
        if (not label or state.linkLevel or state.src[state.pos - 1:state.pos] == "!"
                or state.src[label.end():label.end() + 1] in ("(", "[")):
            return False
        token = state.push("source_reference", "", 0)
        token.meta = {"source_id": label[1], "reference_line": state.src[:state.pos].count("\n")}
        state.pos = label.end()
        return True

    parser.inline.ruler.at("link", source_link)
    parser.inline.ruler.after("link", "source_reference", source_label)
    entries = {}
    for block in parser.parse(references):
        if block.type != "inline":
            continue  # Fenced/indented code and HTML blocks cannot supply entries.
        if any(token.type == "html_inline" for token in block.children or []):
            continue  # Do not interpret raw HTML code/presentation contexts.
        lines = block.content.splitlines()
        labelled = [token for token in block.children or [] if "source_id" in token.meta]
        boundaries = sorted({token.meta["reference_line"] for token in labelled} | {len(lines)})
        endings = dict(zip(boundaries, boundaries[1:]))
        for token in labelled:
            offset = token.meta["reference_line"]
            row = block.map[0] + offset
            # Markdown soft/hard line breaks do not end a reference. A new
            # label, paragraph, list item or code block does; never borrow its
            # destination to complete an earlier entry.
            entry = "\n".join(lines[offset:endings[offset]])
            entries.setdefault(row, []).append((token.meta["source_id"], entry,
                                               token.attrGet("href")))
    for row in entries.values():
        if any(destination is None for _, _, destination in row):
            # Existing standalone [id] entries may use [Title](url) as their URL.
            # Known source-ID links still count, exposing ambiguous mixed entries.
            row = [entry for entry in row if entry[2] is None or entry[0] in known]
        yield row


def citation_issues(report, source_ids, *, source_urls=None, strict=False):
    # Citation labels are fixed source IDs supplied in the evidence blocks.
    labels = re.findall(r"(?<!!)\[([A-Za-z0-9_.-]+)\](?!\()", report)
    known = set(source_ids)
    cited = [label for label in labels if label in known]
    unknown = [label for label in labels if label not in known]
    issues = []
    if not report.strip():
        issues.append("The report is empty.")
    if not cited:
        issues.append("Cite at least one supplied source ID using [source-id].")
    if unknown:
        issues.append("Remove citations to unknown source IDs: " + ", ".join(dict.fromkeys(unknown))[:800])
    if strict:
        parts = re.split(r"^#{1,6}\s+References\s*\r?$", report, flags=re.M | re.I)
        if len(parts) != 2:
            issues.append("Include exactly one Markdown References heading and one entry per cited source.")
            return issues
        body, references = parts
        body_ids = set(re.findall(r"(?<!!)\[([A-Za-z0-9_.-]+)\](?!\()", body)) & known
        if not body_ids:
            issues.append("Add source-ID citations in the report body; references alone do not support claims.")
        entries = {}
        try:
            reference_rows = list(_reference_entries(references, known))
        except (IndexError, RecursionError):
            issues.append("References Markdown could not be parsed; simplify its syntax and retain one entry per cited source.")
            return issues
        for row in reference_rows:
            if len(row) != 1:
                issues.append("Use exactly one source ID per References entry.")
            for identity, line, destination in row:
                entries.setdefault(identity, []).append((line, destination))
        reference_ids = set(entries)
        missing, extra = body_ids - reference_ids, reference_ids - body_ids
        if missing:
            issues.append("Add missing References entries: " + ", ".join(sorted(missing)))
        if extra:
            issues.append("Remove uncited References entries: " + ", ".join(sorted(extra)))
        for identity, lines in entries.items():
            if len(lines) != 1:
                issues.append(f"Use exactly one References entry for {identity}.")
            if source_urls is not None and identity in source_urls:
                allowed = source_urls[identity]
                allowed = {allowed} if isinstance(allowed, str) else set(allowed)
                urls = set()
                for line, destination in lines:
                    if destination is not None:
                        urls.add(destination)
                    for url in re.findall(r"https?://[^\s<>\]]+", line):
                        # Strip prose/Markdown delimiters, not balanced URL
                        # parentheses (common in scholarly and wiki URLs).
                        while url not in allowed and url:
                            if url[-1] in ".,;" or url.endswith(")") and url.count(")") > url.count("("):
                                url = url[:-1]
                            else:
                                break
                        urls.add(url)
                if not urls or not urls <= allowed:
                    issues.append(f"References entry {identity} must use its supplied source URL: " + ", ".join(sorted(allowed)))
    return issues


async def write_and_review(context, question, plan, analysis, evidence, context_plan, *, max_attempts, revision=2,
                           quality=None, source_urls=None):
    feedback, drafts = [], []
    source_ids = [selection.item_id for selection in context_plan.selections]
    for attempt in range(1, max_attempts + 1):
        prefix = f"report.{attempt}"
        writer_input = {
            "question": question, "plan": plan.to_dict(), "analysis": analysis.to_dict(),
            "evidence": evidence, "feedback": feedback,
        }
        if quality is not None:
            writer_input["quality"] = quality.to_dict()
        if revision >= 11 and attempt > 1:
            writer_input["repair"] = {"attempt": attempt, "previous_output": report,
                                      "errors": [{"message": item} for item in feedback]}
        writer_input_ref = None
        if revision >= 11:
            writer_input = {**getattr(context, "agent_input_defaults", {}), **writer_input}
            writer_input_ref = await retain(context, writer_input, prefix + ".write.input.json")
        raw, writer = await invoke_role(context, "baseline.writer", writer_input,
            node_id=prefix + ".write", input_ref=writer_input_ref)
        try:
            report = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise EngineError("INVALID_ROLE_OUTPUT", "Writer report is not UTF-8") from None
        structural = citation_issues(report, source_ids, source_urls=source_urls, strict=revision >= 11)
        if revision >= 4:
            structural.extend(english_report_issues(report))
        if quality is not None and f"Research coverage: {quality.status}" not in report:
            structural.append(f"Include the exact label 'Research coverage: {quality.status}' and explain the material evidence gaps.")
        reviewer_input = {
            "question": question, "plan": plan.to_dict(), "analysis": analysis.to_dict(),
            "evidence": evidence, "report": report,
        }
        if quality is not None:
            reviewer_input["quality"] = quality.to_dict()
        review, reviewer = await decision(context, "baseline.reviewer", reviewer_input, ReportReview, node_id=prefix + ".review")
        feedback = list(dict.fromkeys(structural + review.issues))[:8]
        accepted = not feedback and review.verdict == "accept"
        record = {"attempt": attempt, "draft_ref": writer["output_ref"], "review_ref": reviewer["output_ref"],
                  "structural_issues": structural, "accepted": accepted}
        drafts.append(record)
        async with context.node(prefix + ".validation", "report_validation", {"accepted": accepted}):
            await retain(context, record, prefix + ".validation.json")
            await context.checkpoint({"kind": f"baseline-review/{revision}", "attempt": attempt, "drafts": drafts})
        if accepted:
            return writer["output_ref"], drafts
    raise EngineError("REPORT_REVIEW_FAILED", "Report did not pass bounded review and citation checks",
                      {"issues": feedback, "attempts": max_attempts})


def english_report_issues(report):
    """Reject CJK narrative independently of the model review verdict.

    Bibliographic names remain verbatim in References. This script check catches
    Chinese/Japanese/Korean prose; the Reviewer checks English for other scripts.
    """
    body = re.split(r"^#{1,6}\s+References\s*\r?$", report, maxsplit=1, flags=re.M | re.I)[0]
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\U00020000-\U0002fa1f]", body):
        return ["Write all report headings and narrative in English. Translate non-English prose; retain original bibliographic names only in References."]
    return []
