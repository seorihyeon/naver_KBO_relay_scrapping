from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import traceback
from dataclasses import dataclass, field

import check_data
from gui.jobs import JobContext, JobResult
from src.kbo_ingest.game_json import minimize_game_payload, pretty_game_json
from web_interface import Scrapper


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
    failure_count: int = 0
    skipped_count: int = 0
    failed_files: list[str] = field(default_factory=list)
    validation_failures: list[str] = field(default_factory=list)


@dataclass
class CollectionResult:
    summary: str
    day_logs: list[CollectionLogRecord]
    failed_targets: list[CollectionTarget]
    debug_log_path: str

    def to_job_result(self) -> JobResult:
        total_games = sum(day.game_count for day in self.day_logs)
        total_success = sum(day.success_count for day in self.day_logs)
        total_failures = sum(day.failure_count for day in self.day_logs)
        detail = f"games={total_games} success={total_success} failed={total_failures}"
        return JobResult(
            summary=self.summary,
            detail=detail,
            artifacts={"debug_log_path": self.debug_log_path},
            metrics={
                "games": total_games,
                "success": total_success,
                "failed": total_failures,
                "failed_targets": len(self.failed_targets),
                "day_logs": self.day_logs,
                "failed_target_items": self.failed_targets,
            },
        )


class CollectionService:
    def run(self, request: CollectionRequest, context: JobContext) -> JobResult:
        request.save_dir.mkdir(parents=True, exist_ok=True)
        debug_log_path = request.save_dir / f"scrape_debug_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        day_logs: dict[str, CollectionLogRecord] = {}
        failed_targets: list[CollectionTarget] = []
        scraper: Scrapper | None = None

        try:
            scraper = Scrapper(wait=request.timeout_seconds, path=str(request.save_dir), headless=request.headless)
            context.log("info", "collector started", mode=request.mode, save_dir=str(request.save_dir))
            targets = request.targets or self._discover_targets(scraper, request, context)
            total = max(1, len(targets))
            for index, target in enumerate(targets, start=1):
                context.check_cancelled()
                day_key = target.game_date.isoformat()
                day_log = day_logs.setdefault(day_key, CollectionLogRecord(game_date=day_key))
                day_log.game_count += 1
                outcome = self._fetch_one(scraper, request, target, debug_log_path, context)
                if outcome["status"] == "success":
                    day_log.success_count += 1
                elif outcome["status"] == "skipped":
                    day_log.skipped_count += 1
                else:
                    day_log.failure_count += 1
                    failed_targets.append(target)
                    day_log.failed_files.append(outcome["file_name"])
                    if outcome["validation_reason"]:
                        day_log.validation_failures.append(outcome["validation_reason"])
                context.set_progress(index / total, f"{index}/{total} games processed")
            summary = "Collection completed" if not context.is_cancelled() else "Collection cancelled"
            result = CollectionResult(
                summary=summary,
                day_logs=list(day_logs.values()),
                failed_targets=failed_targets,
                debug_log_path=str(debug_log_path),
            )
            return result.to_job_result()
        except Exception as exc:
            self._append_debug_log(debug_log_path, f"fatal: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            raise
        finally:
            if scraper is not None:
                try:
                    scraper.close()
                except Exception:
                    pass

    def _discover_targets(self, scraper: Scrapper, request: CollectionRequest, context: JobContext) -> list[CollectionTarget]:
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
        context.log("info", "targets discovered", target_count=len(targets))
        return targets

    def _fetch_one(
        self,
        scraper: Scrapper,
        request: CollectionRequest,
        target: CollectionTarget,
        debug_log_path: Path,
        context: JobContext,
    ) -> dict[str, str | None]:
        context.log("info", "collecting game", date=target.game_date.isoformat(), url=target.url)
        target_dir = request.save_dir / str(target.game_date.year)
        target_dir.mkdir(parents=True, exist_ok=True)
        normalized_url = Scrapper.normalize_game_url(target.url)
        file_name = normalized_url.split("/")[-1] + ".json"
        target_path = target_dir / file_name
        existing_outcome = self._try_reuse_existing(target_path)
        if existing_outcome is not None:
            context.log("info", "existing valid file reused", path=str(target_path))
            return {"status": "skipped", "file_name": file_name, "validation_reason": None}

        max_attempts = max(1, int(request.retry_count))
        validation_reason: str | None = None
        for attempt in range(1, max_attempts + 1):
            context.check_cancelled()
            try:
                lineup_data, inning_data, record_data = scraper.get_game_data(normalized_url)
                if not (lineup_data and inning_data and record_data):
                    raise ValueError("missing lineup, relay, or record payload")
                payload = minimize_game_payload(
                    {"lineup": lineup_data, "relay": inning_data, "record": record_data},
                    game_id=Scrapper.extract_game_id(normalized_url),
                    game_url=normalized_url,
                    collected_at=dt.datetime.now(dt.UTC).isoformat(),
                )
                validation = check_data.validate_game(payload)
                if validation.get("ok"):
                    target_path.write_text(pretty_game_json(payload), encoding="utf-8")
                    context.log("info", "game collected", path=str(target_path))
                    return {"status": "success", "file_name": file_name, "validation_reason": None}
                validation_reason = self._summarize_validation(validation)
                self._append_debug_log(debug_log_path, f"{file_name} | validation_failed | {validation_reason}")
            except Exception as exc:
                validation_reason = str(exc)
                self._append_debug_log(
                    debug_log_path,
                    f"{file_name} | attempt={attempt}/{max_attempts} | {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                )
        context.log("error", "game collection failed", date=target.game_date.isoformat(), file_name=file_name)
        return {"status": "failed", "file_name": file_name, "validation_reason": validation_reason}

    def _try_reuse_existing(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        validation = check_data.validate_game(payload)
        return validation if validation.get("ok") else None

    def _append_debug_log(self, path: Path, message: str) -> None:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def _summarize_validation(self, validation: dict) -> str:
        issues = validation.get("issues") or []
        warnings = validation.get("warnings") or []
        parts: list[str] = []
        if issues:
            parts.append(f"issues={issues[0]}")
        if warnings:
            parts.append(f"warnings={warnings[0]}")
        return "; ".join(parts) if parts else "validation failed"
