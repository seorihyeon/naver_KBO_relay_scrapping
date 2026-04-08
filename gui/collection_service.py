from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
import traceback
from typing import Any

import check_data
from gui.jobs import JobContext, JobResult
from src.kbo_ingest.game_json import minimize_game_payload, pretty_game_json
from web_interface import NaverScraper


@dataclass(frozen=True)
class CollectionRequest:
    mode: str
    save_dir: Path
    timeout_seconds: int
    retry_count: int
    headless: bool
    start_date: dt.date
    end_date: dt.date
    season_year: int | None = None
    targets: list["CollectionTarget"] | None = None


@dataclass(frozen=True)
class CollectionTarget:
    game_date: dt.date
    url: str


@dataclass
class CollectionLogRecord:
    game_date: str
    game_count: int = 0
    success_count: int = 0
    anomaly_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    anomaly_files: list[str] = field(default_factory=list)
    anomaly_reasons: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    failed_reasons: list[str] = field(default_factory=list)


@dataclass
class CollectionItemOutcome:
    status: str
    file_name: str
    reason: str | None = None
    validation_issues: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    exception_type: str | None = None
    traceback_text: str | None = None
    attempt: int = 0
    game_id: str | None = None


@dataclass(frozen=True)
class CollectionRunPaths:
    save_dir: Path
    anomaly_dir: Path
    debug_log_path: Path
    anomaly_log_path: Path
    failure_log_path: Path


@dataclass
class CollectionResult:
    summary: str
    day_logs: list[CollectionLogRecord]
    failed_targets: list[CollectionTarget]
    save_dir: str
    anomaly_dir: str
    debug_log_path: str
    anomaly_log_path: str
    failure_log_path: str

    def to_job_result(self) -> JobResult:
        total_games = sum(day.game_count for day in self.day_logs)
        total_success = sum(day.success_count for day in self.day_logs)
        total_anomalies = sum(day.anomaly_count for day in self.day_logs)
        total_failures = sum(day.failure_count for day in self.day_logs)
        total_skipped = sum(day.skipped_count for day in self.day_logs)
        anomaly_files = self._flatten("anomaly_files")
        anomaly_reasons = self._flatten("anomaly_reasons")
        failed_files = self._flatten("failed_files")
        failed_reasons = self._flatten("failed_reasons")
        detail = (
            f"전체 {total_games}경기, 정상 {total_success}, 이상 {total_anomalies}, "
            f"실패 {total_failures}, 재사용 {total_skipped}"
        )
        return JobResult(
            summary=self.summary,
            detail=detail,
            artifacts={
                "save_dir": self.save_dir,
                "anomaly_dir": self.anomaly_dir,
                "debug_log_path": self.debug_log_path,
                "anomaly_log_path": self.anomaly_log_path,
                "failure_log_path": self.failure_log_path,
            },
            metrics={
                "games": total_games,
                "success_count": total_success,
                "anomaly_count": total_anomalies,
                "failure_count": total_failures,
                "skipped_count": total_skipped,
                "success": total_success,
                "anomaly": total_anomalies,
                "failed": total_failures,
                "skipped": total_skipped,
                "anomaly_files": anomaly_files,
                "anomaly_reasons": anomaly_reasons,
                "failed_files": failed_files,
                "failed_reasons": failed_reasons,
                "failed_target_count": len(self.failed_targets),
                "failed_targets": self.failed_targets,
                "failed_target_items": self.failed_targets,
                "day_logs": self.day_logs,
            },
        )

    def _flatten(self, field_name: str) -> list[str]:
        flattened: list[str] = []
        for day in self.day_logs:
            flattened.extend(getattr(day, field_name))
        return flattened


class CollectionService:
    def run(self, request: CollectionRequest, context: JobContext) -> JobResult:
        request.save_dir.mkdir(parents=True, exist_ok=True)
        paths = self._prepare_run_paths(request.save_dir)
        day_logs: dict[str, CollectionLogRecord] = {}
        failed_targets: list[CollectionTarget] = []
        scraper: NaverScraper | None = None

        try:
            scraper = NaverScraper(wait=request.timeout_seconds, path=str(request.save_dir), headless=request.headless)
            context.log("info", "수집 작업 시작", mode=request.mode, save_dir=str(request.save_dir))
            targets = request.targets or self._discover_targets(scraper, request, context)
            total = max(1, len(targets))
            for index, target in enumerate(targets, start=1):
                context.check_cancelled()
                day_key = target.game_date.isoformat()
                day_log = day_logs.setdefault(day_key, CollectionLogRecord(game_date=day_key))
                day_log.game_count += 1
                outcome = self._fetch_one(scraper, request, target, paths, context)
                if outcome.status == "success":
                    day_log.success_count += 1
                elif outcome.status == "anomaly":
                    day_log.anomaly_count += 1
                    day_log.anomaly_files.append(outcome.file_name)
                    if outcome.reason:
                        day_log.anomaly_reasons.append(outcome.reason)
                elif outcome.status == "skipped":
                    day_log.skipped_count += 1
                else:
                    day_log.failure_count += 1
                    failed_targets.append(target)
                    day_log.failed_files.append(outcome.file_name)
                    if outcome.reason:
                        day_log.failed_reasons.append(outcome.reason)
                context.set_progress(index / total, f"{index}/{total} 경기 처리 완료")
            summary = "수집 완료" if not context.is_cancelled() else "수집 취소"
            result = CollectionResult(
                summary=summary,
                day_logs=list(day_logs.values()),
                failed_targets=failed_targets,
                save_dir=str(request.save_dir),
                anomaly_dir=str(paths.anomaly_dir),
                debug_log_path=str(paths.debug_log_path),
                anomaly_log_path=str(paths.anomaly_log_path),
                failure_log_path=str(paths.failure_log_path),
            )
            return result.to_job_result()
        except Exception as exc:
            self._append_debug_log(paths.debug_log_path, f"fatal: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            raise
        finally:
            if scraper is not None:
                try:
                    scraper.close()
                except Exception:
                    pass

    def _prepare_run_paths(self, save_dir: Path) -> CollectionRunPaths:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = save_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        debug_log_path = save_dir / f"scrape_debug_{timestamp}.log"
        anomaly_log_path = logs_dir / f"collection_anomalies_{timestamp}.jsonl"
        failure_log_path = logs_dir / f"collection_failures_{timestamp}.jsonl"
        return CollectionRunPaths(
            save_dir=save_dir,
            anomaly_dir=save_dir / "_anomalies",
            debug_log_path=debug_log_path,
            anomaly_log_path=anomaly_log_path,
            failure_log_path=failure_log_path,
        )

    def _discover_targets(self, scraper: NaverScraper, request: CollectionRequest, context: JobContext) -> list[CollectionTarget]:
        targets: list[CollectionTarget] = []
        if request.mode == "season" and request.season_year is not None:
            for month in range(1, 13):
                active_days = scraper.get_activated_dates_for_month(request.season_year, month)
                for day in active_days:
                    game_date = dt.date(request.season_year, month, day)
                    if not (request.start_date <= game_date <= request.end_date):
                        continue
                    urls = scraper.get_game_urls(request.season_year, month, day)
                    if urls == -1 or not urls:
                        continue
                    targets.extend(CollectionTarget(game_date=game_date, url=url) for url in urls)
        else:
            for game_date, urls in scraper.iter_active_date_urls(request.start_date, request.end_date):
                if urls == -1 or not urls:
                    continue
                targets.extend(CollectionTarget(game_date=game_date, url=url) for url in urls)
        context.log("info", "수집 대상 확인", target_count=len(targets))
        return targets

    def _fetch_one(
        self,
        scraper: NaverScraper,
        request: CollectionRequest,
        target: CollectionTarget,
        paths: CollectionRunPaths,
        context: JobContext,
    ) -> CollectionItemOutcome:
        context.log("info", "경기 수집 중", date=target.game_date.isoformat(), url=target.url)
        normalized_url = NaverScraper.normalize_game_url(target.url)
        game_id = self._extract_game_id(normalized_url)
        file_name = self._build_file_name(normalized_url, game_id)
        target_path = paths.save_dir / str(target.game_date.year) / file_name
        anomaly_path = paths.anomaly_dir / str(target.game_date.year) / file_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        anomaly_path.parent.mkdir(parents=True, exist_ok=True)

        existing_outcome = self._try_reuse_existing(target_path)
        if existing_outcome is not None:
            context.log("info", "기존 정상 파일 재사용", path=str(target_path))
            return CollectionItemOutcome(status="skipped", file_name=file_name, attempt=0, game_id=game_id)

        max_attempts = max(1, int(request.retry_count))
        last_failure: CollectionItemOutcome | None = None
        for attempt in range(1, max_attempts + 1):
            context.check_cancelled()
            try:
                lineup_data, inning_data, record_data = scraper.get_game_data(normalized_url)
                if not (lineup_data and inning_data and record_data):
                    raise ValueError("missing lineup, relay, or record payload")
                payload = minimize_game_payload(
                    {"lineup": lineup_data, "relay": inning_data, "record": record_data},
                    game_id=game_id,
                    game_url=normalized_url,
                    collected_at=dt.datetime.now(dt.UTC).isoformat(),
                )

                try:
                    validation = check_data.validate_game(payload)
                except Exception as exc:
                    anomaly_outcome = CollectionItemOutcome(
                        status="anomaly",
                        file_name=file_name,
                        reason=f"validation exception: {type(exc).__name__}: {exc}",
                        validation_issues=[f"validation exception: {type(exc).__name__}: {exc}"],
                        validation_warnings=[],
                        exception_type=type(exc).__name__,
                        traceback_text=traceback.format_exc(),
                        attempt=attempt,
                        game_id=game_id,
                    )
                    self._append_debug_log(
                        paths.debug_log_path,
                        f"{file_name} | validation_exception | {type(exc).__name__}: {exc}\n{anomaly_outcome.traceback_text}",
                    )
                    anomaly_path.write_text(pretty_game_json(payload), encoding="utf-8")
                    self._append_structured_log(
                        paths.anomaly_log_path,
                        self._build_structured_log_record(target=target, url=normalized_url, outcome=anomaly_outcome),
                    )
                    context.log(
                        "warn",
                        "이상 데이터로 분리 저장",
                        path=str(anomaly_path),
                        reason=anomaly_outcome.reason,
                    )
                    return anomaly_outcome

                if validation.get("ok"):
                    target_path.write_text(pretty_game_json(payload), encoding="utf-8")
                    context.log("info", "정상 수집 저장 완료", path=str(target_path))
                    return CollectionItemOutcome(status="success", file_name=file_name, attempt=attempt, game_id=game_id)

                anomaly_outcome = CollectionItemOutcome(
                    status="anomaly",
                    file_name=file_name,
                    reason=self._summarize_validation(validation),
                    validation_issues=list(validation.get("issues") or []),
                    validation_warnings=list(validation.get("warnings") or []),
                    attempt=attempt,
                    game_id=game_id,
                )
                self._append_debug_log(paths.debug_log_path, f"{file_name} | validation_failed | {anomaly_outcome.reason}")
                anomaly_path.write_text(pretty_game_json(payload), encoding="utf-8")
                self._append_structured_log(
                    paths.anomaly_log_path,
                    self._build_structured_log_record(target=target, url=normalized_url, outcome=anomaly_outcome),
                )
                context.log(
                    "warn",
                    "이상 데이터로 분리 저장",
                    path=str(anomaly_path),
                    reason=anomaly_outcome.reason,
                )
                return anomaly_outcome
            except Exception as exc:
                last_failure = CollectionItemOutcome(
                    status="failed",
                    file_name=file_name,
                    reason=str(exc),
                    exception_type=type(exc).__name__,
                    traceback_text=traceback.format_exc(),
                    attempt=attempt,
                    game_id=game_id,
                )
                self._append_debug_log(
                    paths.debug_log_path,
                    f"{file_name} | attempt={attempt}/{max_attempts} | {type(exc).__name__}: {exc}\n{last_failure.traceback_text}",
                )

        if last_failure is None:
            last_failure = CollectionItemOutcome(
                status="failed",
                file_name=file_name,
                reason="collection failed",
                attempt=max_attempts,
                game_id=game_id,
            )
        self._append_structured_log(
            paths.failure_log_path,
            self._build_structured_log_record(target=target, url=normalized_url, outcome=last_failure),
        )
        context.log(
            "error",
            "경기 수집 실패",
            date=target.game_date.isoformat(),
            file_name=file_name,
            reason=last_failure.reason,
        )
        return last_failure

    def _build_file_name(self, normalized_url: str, game_id: str | None) -> str:
        if game_id:
            return f"{game_id}.json"
        stem = normalized_url.rstrip("/").split("/")[-1] or "unknown_game"
        return f"{stem}.json"

    def _extract_game_id(self, normalized_url: str) -> str | None:
        try:
            game_id = NaverScraper.extract_game_id(normalized_url)
        except Exception:
            return None
        return game_id or None

    def _build_structured_log_record(
        self,
        *,
        target: CollectionTarget,
        url: str,
        outcome: CollectionItemOutcome,
    ) -> dict[str, Any]:
        return {
            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            "game_date": target.game_date.isoformat(),
            "url": url,
            "game_id": outcome.game_id,
            "file_name": outcome.file_name,
            "status": outcome.status,
            "attempt": outcome.attempt,
            "reason": outcome.reason or "",
            "validation_issues": list(outcome.validation_issues),
            "validation_warnings": list(outcome.validation_warnings),
            "exception_type": outcome.exception_type,
            "traceback": outcome.traceback_text,
        }

    def _try_reuse_existing(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validation = check_data.validate_game(payload)
        except Exception:
            return None
        return validation if validation.get("ok") else None

    def _append_debug_log(self, path: Path, message: str) -> None:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def _append_structured_log(self, path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _summarize_validation(self, validation: dict[str, Any]) -> str:
        issues = validation.get("issues") or []
        warnings = validation.get("warnings") or []
        parts: list[str] = []
        if issues:
            parts.append(f"issues={issues[0]}")
        if warnings:
            parts.append(f"warnings={warnings[0]}")
        return "; ".join(parts) if parts else "validation failed"
