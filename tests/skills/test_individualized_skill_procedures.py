"""Static source invariants for individual Skill procedures (not live API evals)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def read_skill(path):
    return (ROOT / path / "SKILL.md").read_text(encoding="utf-8")

def test_notion_versioning_and_data_source_parent():
    s = read_skill("skills/productivity/notion")
    assert "version: 1.1.0" in s
    assert "not the latest version" in s
    assert "2025-09-03" in s and "2026-03-11" in s
    assert '"type": "data_source_id"' in s
    assert '"initial_data_source"' in s
    assert "POST /v1/databases" in s
    assert "has_more" in s and "next_cursor" in s
    assert "read-back" in s.lower()

def test_mcporter_installation_and_untrusted_discovery():
    s = read_skill("skills/mcp/mcporter")
    assert "version: 1.1.0" in s
    assert "download and execute" in s
    assert "Node 24+" in s
    assert "untrusted" in s
    assert "explicit authorization" in s
    assert "do not blindly replay" in s

def test_fastmcp_requires_file_root_and_isolated_installs():
    s = read_skill("optional-skills/mcp/fastmcp")
    assert "version: 1.1.0" in s
    assert "MCP_FILE_ROOT" in s
    assert "2026-08-31" in s
    assert "TOCTOU" in s
    assert "authorization" in s.lower()
    assert "isolated" in s


def test_1password_never_captures_or_echoes_secrets():
    s = read_skill("optional-skills/security/1password")
    assert "version: 1.1.0" in s
    assert "harness.yaml" in s
    assert "tmux capture-pane" in s
    assert "Do not run" in s and "op read" in s
    assert 'export OP_SERVICE_ACCOUNT_TOKEN="your-token-here"' not in s
    assert "Never print" in s
    assert "approved" in s.lower()

def test_himalaya_does_not_pipe_unreviewed_templates_to_send():
    s = read_skill("skills/email/himalaya")
    assert "version: 1.1.0" in s
    assert "harness.yaml" in s
    assert "authorized external send" in s
    assert "untrusted" in s.lower()
    assert "unknown" in s.lower()
    assert "curl -sSL https://raw.githubusercontent.com/pimalaya/himalaya/master/install.sh" not in s
    assert "sed 's/^To:.*/To: newrecipient@example.com/' | himalaya template send" not in s

def test_webhook_routes_need_loopback_signature_replay_and_external_scope():
    s = read_skill("skills/devops/webhook-subscriptions")
    assert "version: 1.1.0" in s
    assert "harness.yaml" in s
    assert 'host: "127.0.0.1"' in s
    assert 'host: "0.0.0.0"' not in s
    assert "replay" in s.lower() and "untrusted" in s.lower()
    assert "do not enable it automatically" in s.lower()
    assert "read back" in s.lower()
