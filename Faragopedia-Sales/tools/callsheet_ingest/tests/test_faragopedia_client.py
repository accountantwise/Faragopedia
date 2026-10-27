"""Faragopedia API client: retry-on-reset behaviour, auth header assembly, and the
endpoint wrappers' error handling.

subprocess.run is mocked because it shells out to a real network call — the one
dependency here that TDD's own guidance says to mock rather than exercise for real.
Everything else (retry counting, header construction, response parsing) runs for real.
"""

from types import SimpleNamespace

import pytest

from faragopedia_client import Faragopedia, FaragopediaError, Response


def make_client(**kwargs) -> Faragopedia:
    defaults = dict(base_url="https://faragopedia-api.example.uk", cf_id=None,
                     cf_secret=None, api_key="test-key", attempts=3)
    defaults.update(kwargs)
    return Faragopedia(**defaults)


def fake_run(returncode=0, stdout="", stderr=""):
    return lambda cmd, capture_output, text, encoding: SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr=stderr)


# --- construction ----------------------------------------------------------------------

def test_init_raises_when_base_url_missing(monkeypatch):
    monkeypatch.delenv("FARAGOPEDIA_API_URL", raising=False)
    with pytest.raises(FaragopediaError, match="FARAGOPEDIA_API_URL"):
        Faragopedia()


def test_init_reads_base_url_from_env_when_not_passed(monkeypatch):
    monkeypatch.setenv("FARAGOPEDIA_API_URL", "https://example.uk/")
    client = Faragopedia()
    assert client.base == "https://example.uk"  # trailing slash stripped


# --- Response ---------------------------------------------------------------------------

def test_response_ok_true_for_2xx():
    assert Response(200, "{}").ok is True
    assert Response(299, "{}").ok is True


def test_response_ok_false_for_4xx():
    assert Response(404, "").ok is False


def test_response_json_parses_body():
    assert Response(200, '{"a": 1}').json() == {"a": 1}


def test_response_json_none_for_empty_body():
    assert Response(204, "   ").json() is None


# --- auth header assembly ----------------------------------------------------------------

def test_auth_args_includes_api_key_header():
    client = make_client(api_key="secret-key")
    args = client._auth_args()
    assert "X-Api-Key: secret-key" in args


def test_auth_args_includes_cf_access_headers_when_set():
    client = make_client(cf_id="cid", cf_secret="csecret")
    args = client._auth_args()
    assert "CF-Access-Client-Id: cid" in args
    assert "CF-Access-Client-Secret: csecret" in args


def test_auth_args_omits_cf_headers_when_unset():
    client = make_client(cf_id=None, cf_secret=None)
    args = client._auth_args()
    assert not any("CF-Access" in a for a in args)


def test_auth_args_always_sets_curl_user_agent():
    # The default Python/requests user agent is rejected outright by Cloudflare's WAF
    # (error 1010) before the request reaches the backend.
    client = make_client()
    args = client._auth_args()
    assert "User-Agent: curl/8.5.0" in args


# --- _call: retry on transient curl failure, not on a real 4xx --------------------------

def test_call_succeeds_first_try(monkeypatch):
    client = make_client()
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout="hello\n200"))
    resp = client._call("GET", "/api/thing")
    assert resp.status == 200
    assert resp.body == "hello"


def test_call_retries_on_retryable_curl_exit_code_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def run(cmd, capture_output, text, encoding):
        calls["n"] += 1
        if calls["n"] < 3:
            return SimpleNamespace(returncode=56, stdout="", stderr="recv failure")
        return SimpleNamespace(returncode=0, stdout="ok\n200", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    client = make_client(attempts=5)
    resp = client._call("GET", "/api/thing")
    assert resp.status == 200
    assert calls["n"] == 3


def test_call_raises_after_exhausting_retryable_attempts(monkeypatch):
    monkeypatch.setattr("subprocess.run", fake_run(returncode=56, stdout="", stderr="recv failure"))
    client = make_client(attempts=2)
    with pytest.raises(FaragopediaError, match="failed after 2 attempts"):
        client._call("GET", "/api/thing")


def test_call_does_not_retry_non_retryable_curl_exit_code(monkeypatch):
    calls = {"n": 0}

    def run(cmd, capture_output, text, encoding):
        calls["n"] += 1
        return SimpleNamespace(returncode=1, stdout="", stderr="bad url")

    monkeypatch.setattr("subprocess.run", run)
    client = make_client(attempts=5)
    with pytest.raises(FaragopediaError, match="not retryable"):
        client._call("GET", "/api/thing")
    assert calls["n"] == 1  # must fail on first attempt, no wasted retries


def test_call_treats_unparseable_output_as_retryable(monkeypatch):
    calls = {"n": 0}

    def run(cmd, capture_output, text, encoding):
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(returncode=0, stdout="garbage with no status code", stderr="")
        return SimpleNamespace(returncode=0, stdout="ok\n200", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    client = make_client(attempts=3)
    resp = client._call("GET", "/api/thing")
    assert resp.status == 200


# --- endpoint wrappers -------------------------------------------------------------------

def test_entity_types_raises_on_non_ok(monkeypatch):
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout="oops\n500"))
    client = make_client()
    with pytest.raises(FaragopediaError, match="entity-types"):
        client.entity_types()


def test_create_folder_treats_already_exists_400_as_not_created(monkeypatch):
    body = '{"detail": "folder already exists"}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n400"))
    client = make_client()
    created, msg = client.create_folder("callsheets", "Callsheets")
    assert created is False
    assert "already exists" in msg


def test_create_folder_raises_on_other_400(monkeypatch):
    body = '{"detail": "validation error"}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n400"))
    client = make_client()
    with pytest.raises(FaragopediaError, match="validation error"):
        client.create_folder("callsheets", "Callsheets")


def test_create_folder_returns_created_true_on_success(monkeypatch):
    body = '{"message": "created"}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n201"))
    client = make_client()
    created, msg = client.create_folder("callsheets", "Callsheets")
    assert created is True
    assert msg == "created"


def test_verify_folder_schema_reports_missing_fields(monkeypatch):
    body = '{"callsheets": {"fields": [{"name": "type"}, {"name": "name"}]}}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n200"))
    client = make_client()
    missing = client.verify_folder_schema(
        "callsheets", [{"name": "type"}, {"name": "name"}, {"name": "client"}])
    assert missing == ["missing field 'client'"]


def test_verify_folder_schema_reports_unregistered_folder(monkeypatch):
    body = '{}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n200"))
    client = make_client()
    missing = client.verify_folder_schema("callsheets", [{"name": "type"}])
    assert missing == ["folder 'callsheets' is not a registered entity type"]


def test_import_pages_raises_with_detail_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    body = '{"detail": "bad upload"}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n422"))
    client = make_client()
    with pytest.raises(FaragopediaError, match="bad upload"):
        client.import_pages("callsheets", {"job-526.md": "# content"})


def test_put_job_links_returns_parsed_json_on_success(monkeypatch):
    body = '{"count": 3}'
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout=f"{body}\n200"))
    client = make_client()
    result = client.put_job_links({"job-526": {"provider": "dropbox"}})
    assert result == {"count": 3}


def test_get_page_raises_on_non_ok(monkeypatch):
    monkeypatch.setattr("subprocess.run", fake_run(returncode=0, stdout="not found\n404"))
    client = make_client()
    with pytest.raises(FaragopediaError, match="get_page"):
        client.get_page("callsheets/job-526")
