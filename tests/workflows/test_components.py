"""Regression checks for saved evidence and extension-free node execution."""
import copy

import pytest

from ebd.contracts import EngineError, digest_bytes
from ebd.engine.providers.tokenization import TokenMeter
from ebd.extensions import ExtensionRegistry, HookDispatcher
from ebd.workflows import SourceManifest, SourceRecord, WorkflowContext
from ebd.workflows.components.context_selection import assemble_context
from ebd.workflows.components.discovery import candidates, discover


class Port:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.events, self.updates, self.reads, self.publications = [], [], [], []

    def assert_active(self):
        pass

    async def update(self, **fields):
        self.updates.append(copy.deepcopy(fields))

    async def emit(self, kind, payload, **kwargs):
        self.events.append((kind, copy.deepcopy(payload)))

    async def run_tool(self, name, args):
        assert name == "document.read", "Context assembly must read saved snapshots"
        self.reads.append(args)
        return {"status": "succeeded", "recording": {"status": "complete"},
            "result": self.chunks.pop(0), "invocation": {"action_id": "action-" + str(len(self.reads))}}

    async def publish(self, content, media_type, filename):
        self.publications.append((content, media_type, filename))
        return {"store_id": "test", "artifact_id": "selected"}


def context(port):
    return WorkflowContext("run-test", "test-model", port,
        HookDispatcher(ExtensionRegistry(), port.emit), TokenMeter())


@pytest.mark.asyncio
async def test_default_nodes_accept_query_and_long_url_without_optional_hooks():
    port = Port()
    ctx = context(port)
    async with ctx.node("discovery.0", "discovery", {"query": "some research terms"}):
        pass
    async with ctx.node("acquisition.0", "acquisition", {"url": "https://example.org/" + "a" * 1500}):
        pass
    assert all(node["status"] == "succeeded" for node in ctx.nodes.values())
    assert sum(kind == "workflow.node.completed" for kind, _ in port.events) == 2


@pytest.mark.asyncio
async def test_node_failures_leave_a_failed_node_and_preserve_original_error():
    port = Port()
    ctx = context(port)
    with pytest.raises(EngineError) as error:
        async with ctx.node("test.failure", "source_read"):
            raise EngineError("INTEGRITY_ERROR", "Controlled source integrity failure")
    assert error.value.code == "INTEGRITY_ERROR"
    assert ctx.nodes["test.failure"]["status"] == "failed"
    assert port.events[-1][0] == "workflow.node.failed"


@pytest.mark.asyncio
async def test_continuation_selects_matching_retained_bytes_with_auditable_offsets():
    first = "unrelated overview " * 40
    second = "needle 证据研究 " * 100
    offset = len(first.encode())
    chunks = [{"text": first, "has_more_in_requested_range": True, "continuation": "opaque-cursor",
               "truncated": True, "spans": [{"start_byte": 0, "end_byte": offset}]},
              {"text": second, "has_more_in_requested_range": False, "truncated": False,
               "spans": [{"start_byte": offset, "end_byte": offset + len(second.encode())}]}]
    port = Port(chunks)
    source = SourceRecord(item_id="source-1", url="https://example.org/evidence", status="succeeded",
        snapshot_ref={"store_id": "test", "snapshot_id": "snapshot-1"},
        line_count=1, recording_status="complete", persistence_state="committed")
    text, plan = await assemble_context(context(port), SourceManifest(items=[source]), "needle 证据研究",
        token_budget=512, max_text_bytes=1200, max_scan_bytes=8192)
    chosen = plan.selections[0]
    assert port.reads[0]["continuation"] is None
    assert port.reads[1]["continuation"] == "opaque-cursor"
    assert chosen.start_byte == offset and chosen.source_read_action_id == "action-2"
    rendered = text.split("Content:\n", 1)[1]
    assert chosen.end_byte == offset + len(rendered.encode())
    assert chosen.text_sha256 == digest_bytes(rendered.encode())
    assert second.startswith(rendered) and chosen.truncated
    assert plan.measurement.kind == "estimated" and plan.measurement.count <= 512
    assert len(text.encode()) <= 1200 and port.publications[0][0] == text.encode()


def test_discovery_projects_provider_schemas_without_treating_snippets_as_evidence():
    web = candidates("web.search", {"results": [{"url": "https://example.org/a", "snippet": "unread body"}]}, "discovery-1")
    crossref = candidates("scholar.crossref.search", {"results": [{"doi_url": "https://doi.org/10.1/test",
        "links": [{"url": "https://example.org/paper.pdf", "content_type": "application/pdf"}]}]}, "discovery-2")
    openalex = candidates("scholar.openalex.search", {"results": [{"open_access": {"oa_url": "https://example.org/open"},
        "primary_location": {"pdf_url": "https://example.org/other.pdf"}}]}, "discovery-3")
    assert [rows[0]["url"] for rows in (web, crossref, openalex)] == [
        "https://example.org/a", "https://example.org/paper.pdf", "https://example.org/open"]
    assert all(set(row) == {"url", "discovery_ref", "reason"} for rows in (web, crossref, openalex) for row in rows)


@pytest.mark.asyncio
async def test_empty_discovery_still_uses_the_configured_fallback():
    class DiscoveryPort(Port):
        async def run_tool(self, name, args):
            self.reads.append(name)
            rows = [] if name == "web.search" else [{"doi_url": "https://doi.org/10.1/test"}]
            return {"status": "succeeded", "recording": {"status": "complete"}, "result": {"results": rows}}
    port = DiscoveryPort()
    items, archived = await discover(context(port), ["some query"], ["web.search", "scholar.crossref.search"], 5)
    assert port.reads == ["web.search", "scholar.crossref.search"]
    assert len(archived) == 2 and items[0].url == "https://doi.org/10.1/test"
