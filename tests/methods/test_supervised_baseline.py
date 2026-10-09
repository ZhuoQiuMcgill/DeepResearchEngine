"""Fetch supervision changes acquisition, not the baseline research policy."""
import json
from pathlib import Path

from deepresearch.bootstrap import create_method_registry
from deepresearch.methods import baseline


def test_revision_thirteen_changes_only_the_fetch_pin():
    resources = Path(baseline.__file__).parent / 'resources'
    old = json.loads((resources / '12/method.json').read_text(encoding='utf8'))
    new = json.loads((resources / '13/method.json').read_text(encoding='utf8'))
    assert new['revision'] == 13
    assert new['tool_revisions']['web.fetch'] == 3
    old['revision'] = new['revision']
    old['description'] = new['description']
    old['tool_revisions']['web.fetch'] = 3
    assert new == old
    for filename in ('input.schema.json', 'parameters.schema.json'):
        assert (resources / '12' / filename).read_bytes() == (resources / '13' / filename).read_bytes()
    assert any(m['method_id'] == 'baseline' and m['revision'] == 13
        for m in create_method_registry().list())
