"""The R2 client is made once per process and kept (a new one per call cost ~0.3-0.7 s on R2)."""
import logging
from concurrent.futures import ThreadPoolExecutor

from apps.media import storage


def test_one_client_is_kept_and_shared_between_threads():
    first = storage.client()
    assert storage.client() is first
    with ThreadPoolExecutor(4) as pool:
        assert set(pool.map(lambda _: storage.client(), range(8))) == {first}
    storage.put("k", b"x", "text/plain")
    assert storage.read("k") == b"x"


def test_other_settings_make_a_new_client(settings):
    first = storage.client()
    settings.S3_REGION = "eu-west-1"
    assert storage.client() is not first


def test_a_forked_process_makes_its_own():
    first = storage.client()
    storage._forget()                 # what os.register_at_fork runs in the child
    assert storage.client() is not first


def test_r2_call_times_are_logged_only_when_asked(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="vayu.events")
    storage._forget()
    storage.exists("nothing")
    assert not [r for r in caplog.records if r.getMessage() == "r2.call"]
    monkeypatch.setenv("R2_CALL_LOG", "1")
    storage._forget()
    storage.put("k", b"x", "text/plain")
    call = next(r for r in caplog.records if r.getMessage() == "r2.call")
    assert (call.op, call.status) == ("PutObject", 200)
    assert call.duration_ms >= 0
    storage._finished(context={}, model=None, http_response=None)    # no start: nothing logged
    storage._forget()
