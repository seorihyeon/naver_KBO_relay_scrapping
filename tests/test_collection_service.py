import datetime as dt
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import services.collection_service as collection_service_module
from services.collection_service import CollectionRequest, CollectionService, CollectionTarget


class DummyContext:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str, dict]] = []
        self.progress_updates: list[tuple[float, str | None]] = []

    def log(self, level: str, message: str, **context):
        self.logs.append((level, message, context))

    def set_progress(self, progress: float, message: str | None = None):
        self.progress_updates.append((progress, message))

    def is_cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        return None


def _make_request(tmp_path: Path, targets: list[CollectionTarget], retry_count: int = 1) -> CollectionRequest:
    return CollectionRequest(
        mode="period",
        save_dir=tmp_path,
        timeout_seconds=8,
        retry_count=retry_count,
        headless=True,
        start_date=dt.date(2026, 4, 8),
        end_date=dt.date(2026, 4, 8),
        targets=targets,
    )


def _make_target(game_id: str, game_date: dt.date | None = None) -> CollectionTarget:
    return CollectionTarget(game_date=game_date or dt.date(2026, 4, 8), url=f"/game/{game_id}")


def _build_fake_scraper(responses: dict[str, object]):
    class FakeScraper:
        calls: list[str] = []
        closed = False

        def __init__(self, wait=10, path="games", headless=True):
            self.wait = wait
            self.path = path
            self.headless = headless

        def close(self):
            type(self).closed = True

        def get_game_data(self, game_url):
            normalized = type(self).normalize_game_url(game_url)
            type(self).calls.append(normalized)
            response = responses[normalized]
            if isinstance(response, Exception):
                raise response
            return response

        @classmethod
        def normalize_game_url(cls, game_url):
            raw = str(game_url or "").strip()
            if raw.startswith("http://") or raw.startswith("https://"):
                return raw
            return f"https://m.sports.naver.com{raw}"

        @classmethod
        def extract_game_id(cls, game_url):
            return cls.normalize_game_url(game_url).split("/game/", 1)[-1].split("/", 1)[0]

    return FakeScraper


def _fake_minimize_game_payload(payload, *, game_id, game_url, collected_at):
    return {
        "schema_version": 2,
        "game_id": game_id,
        "game_source": {"url": game_url},
        "collected_at": collected_at,
        "lineup": {"source": "lineup"},
        "relay": [{"source": "relay"}],
        "record": {"source": "record"},
    }


def _read_jsonl(path: str) -> list[dict]:
    content = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in content if line.strip()]


def test_run_saves_successful_collection_to_normal_path(tmp_path, monkeypatch):
    target = _make_target("20260408SSKT02026")
    normalized_url = f"https://m.sports.naver.com/game/{target.url.split('/')[-1]}"
    fake_scraper = _build_fake_scraper(
        {normalized_url: ({"lineup": True}, [{"relay": True}], {"record": True})}
    )
    monkeypatch.setattr(collection_service_module, "NaverScraper", fake_scraper)
    monkeypatch.setattr(collection_service_module, "minimize_game_payload", _fake_minimize_game_payload)
    monkeypatch.setattr(
        collection_service_module.ValidationService,
        "validate_game",
        lambda self, payload: {"ok": True, "issues": [], "warnings": []},
    )

    result = CollectionService().run(_make_request(tmp_path, [target]), DummyContext())

    saved_path = tmp_path / "2026" / "20260408SSKT02026.json"
    assert saved_path.exists()
    assert not (tmp_path / "_anomalies" / "2026" / "20260408SSKT02026.json").exists()
    assert result.metrics["success_count"] == 1
    assert result.metrics["anomaly_count"] == 0
    assert result.metrics["failure_count"] == 0
    assert result.metrics["skipped_count"] == 0
    assert result.metrics["failed_targets"] == []
    assert not Path(result.artifacts["debug_log_path"]).exists()
    assert not Path(result.artifacts["anomaly_log_path"]).exists()
    assert not Path(result.artifacts["failure_log_path"]).exists()


def test_run_saves_validation_failure_as_anomaly_and_excludes_retry_target(tmp_path, monkeypatch):
    target = _make_target("20260408NCKT02026")
    normalized_url = f"https://m.sports.naver.com/game/{target.url.split('/')[-1]}"
    fake_scraper = _build_fake_scraper(
        {normalized_url: ({"lineup": True}, [{"relay": True}], {"record": True})}
    )
    monkeypatch.setattr(collection_service_module, "NaverScraper", fake_scraper)
    monkeypatch.setattr(collection_service_module, "minimize_game_payload", _fake_minimize_game_payload)
    monkeypatch.setattr(
        collection_service_module.ValidationService,
        "validate_game",
        lambda self, payload: {"ok": False, "issues": ["relay mismatch"], "warnings": ["scoreboard warning"]},
    )

    result = CollectionService().run(_make_request(tmp_path, [target]), DummyContext())

    anomaly_path = tmp_path / "_anomalies" / "2026" / "20260408NCKT02026.json"
    assert anomaly_path.exists()
    assert not (tmp_path / "2026" / "20260408NCKT02026.json").exists()
    assert result.metrics["success_count"] == 0
    assert result.metrics["anomaly_count"] == 1
    assert result.metrics["failure_count"] == 0
    assert result.metrics["failed_targets"] == []
    assert Path(result.artifacts["anomaly_log_path"]).exists()
    assert not Path(result.artifacts["failure_log_path"]).exists()

    anomaly_log_records = _read_jsonl(result.artifacts["anomaly_log_path"])
    assert len(anomaly_log_records) == 1
    assert anomaly_log_records[0]["status"] == "anomaly"
    assert anomaly_log_records[0]["file_name"] == "20260408NCKT02026.json"
    assert anomaly_log_records[0]["validation_issues"] == ["relay mismatch"]
    assert anomaly_log_records[0]["validation_warnings"] == ["scoreboard warning"]
    assert "relay mismatch" in anomaly_log_records[0]["reason"]


def test_run_logs_failed_collection_and_includes_retry_target(tmp_path, monkeypatch):
    target = _make_target("20260408LGKT02026")
    normalized_url = f"https://m.sports.naver.com/game/{target.url.split('/')[-1]}"
    fake_scraper = _build_fake_scraper({normalized_url: RuntimeError("network down")})
    monkeypatch.setattr(collection_service_module, "NaverScraper", fake_scraper)
    monkeypatch.setattr(collection_service_module, "minimize_game_payload", _fake_minimize_game_payload)
    monkeypatch.setattr(
        collection_service_module.ValidationService,
        "validate_game",
        lambda self, payload: {"ok": True, "issues": [], "warnings": []},
    )

    result = CollectionService().run(_make_request(tmp_path, [target], retry_count=2), DummyContext())

    assert result.metrics["success_count"] == 0
    assert result.metrics["anomaly_count"] == 0
    assert result.metrics["failure_count"] == 1
    assert result.metrics["failed_targets"] == [target]
    assert result.metrics["failed_target_count"] == 1
    assert Path(result.artifacts["failure_log_path"]).exists()

    failure_log_records = _read_jsonl(result.artifacts["failure_log_path"])
    assert len(failure_log_records) == 1
    assert failure_log_records[0]["status"] == "failed"
    assert failure_log_records[0]["attempt"] == 2
    assert failure_log_records[0]["exception_type"] == "RuntimeError"
    assert "network down" in failure_log_records[0]["reason"]
    assert "RuntimeError" in failure_log_records[0]["traceback"]


def test_run_reuses_existing_valid_file_as_skipped(tmp_path, monkeypatch):
    target = _make_target("20260408LTKT02026")
    cached_path = tmp_path / "2026" / "20260408LTKT02026.json"
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_text(json.dumps({"cached": True}, ensure_ascii=False), encoding="utf-8")

    fake_scraper = _build_fake_scraper({})
    monkeypatch.setattr(collection_service_module, "NaverScraper", fake_scraper)
    monkeypatch.setattr(collection_service_module, "minimize_game_payload", _fake_minimize_game_payload)
    monkeypatch.setattr(
        collection_service_module.ValidationService,
        "validate_game",
        lambda self, payload: {"ok": bool(payload.get("cached")), "issues": [], "warnings": []},
    )

    result = CollectionService().run(_make_request(tmp_path, [target]), DummyContext())

    assert result.metrics["success_count"] == 0
    assert result.metrics["anomaly_count"] == 0
    assert result.metrics["failure_count"] == 0
    assert result.metrics["skipped_count"] == 1
    assert result.metrics["failed_targets"] == []
    assert fake_scraper.calls == []


def test_failed_targets_only_include_actual_failures_for_retry(tmp_path, monkeypatch):
    success_target = _make_target("20260408OBKT02026")
    anomaly_target = _make_target("20260408SSWO02026")
    failed_target = _make_target("20260408HHHT02026")
    success_url = f"https://m.sports.naver.com/game/{success_target.url.split('/')[-1]}"
    anomaly_url = f"https://m.sports.naver.com/game/{anomaly_target.url.split('/')[-1]}"
    failed_url = f"https://m.sports.naver.com/game/{failed_target.url.split('/')[-1]}"
    fake_scraper = _build_fake_scraper(
        {
            success_url: ({"lineup": True}, [{"relay": True}], {"record": True}),
            anomaly_url: ({"lineup": True}, [{"relay": True}], {"record": True}),
            failed_url: TimeoutError("timed out"),
        }
    )
    monkeypatch.setattr(collection_service_module, "NaverScraper", fake_scraper)
    monkeypatch.setattr(collection_service_module, "minimize_game_payload", _fake_minimize_game_payload)

    def fake_validate(self, payload):
        if payload["game_id"] == "20260408SSWO02026":
            return {"ok": False, "issues": ["record mismatch"], "warnings": []}
        return {"ok": True, "issues": [], "warnings": []}

    monkeypatch.setattr(collection_service_module.ValidationService, "validate_game", fake_validate)

    result = CollectionService().run(
        _make_request(tmp_path, [success_target, anomaly_target, failed_target], retry_count=1),
        DummyContext(),
    )

    assert result.metrics["success_count"] == 1
    assert result.metrics["anomaly_count"] == 1
    assert result.metrics["failure_count"] == 1
    assert result.metrics["failed_targets"] == [failed_target]
    assert anomaly_target not in result.metrics["failed_targets"]
