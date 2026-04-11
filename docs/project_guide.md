# KBO Scrapping Analysis 가이드

## 1. 프로젝트가 하는 일

이 저장소는 KBO 경기의 Naver 중계 JSON을 수집하고, 소스 오류가 있는 경기를 구조화된 GUI에서 보정한 뒤, 최소 스키마 JSON을 PostgreSQL에 적재하고 검증/리플레이까지 수행하는 도구 모음입니다.

핵심 목표는 다음 네 가지입니다.

- 수집: 경기별 `lineup / relay / record`를 재현 가능하게 수집
- 보정: 자유 텍스트 편집이 아니라 야구 의미를 유지하는 구조화 보정
- 적재: 최소 스키마 JSON을 raw/normalized 테이블로 일관되게 적재
- 검증/리플레이: 소스 이상과 로더 이상을 분리해 검증하고, 정규화된 상태를 GUI에서 재생

## 2. 현재 저장소 구조

- `kbo_integrated_gui.py`: 통합 GUI 진입점
- `src/kbo_ingest/game_validation.py`: 최소 스키마 기반 검증
- `services/json_migration_service.py`, `scripts/migrate_game_json.py`: 저장 JSON 마이그레이션 로직과 실행 진입점
- `services/postgres_loader_service.py`, `scripts/postgres_loader.py`: manifest 생성, DB 적재, 검증, sample-loop 실행
- `src/kbo_ingest/`: 스키마 최소화, 보정, 정규화, 적재, 검증의 핵심 도메인 로직
- `tabs/`: GUI 탭 컨트롤러
- `gui/`: 앱 셸, 상태, 공용 작업 인프라, 재사용 컴포넌트, 리플레이 보조 로직
- `sql/schema.sql`: PostgreSQL 스키마
- `tests/`: GUI 순수 로직, 정규화, 보정, 적재 관련 테스트

도메인 경계는 아래처럼 유지합니다.

- 수집: `infrastructure/naver_scraper.py`, `services/collection_service.py`, `tabs/collection_tab.py`
- 보정/에디터: `src/kbo_ingest/editor_core.py`, `src/kbo_ingest/correction_engine.py`, `tabs/editor_tab.py`
- 적재: `src/kbo_ingest/ingest_raw.py`, `src/kbo_ingest/normalize_game.py`, `src/kbo_ingest/pipeline.py`, `services/postgres_loader_service.py`, `scripts/postgres_loader.py`
- 검증/리플레이: `src/kbo_ingest/game_validation.py`, `src/kbo_ingest/validation.py`, `core/replay/*`, `gui/replay_renderers.py`, `tabs/replay_tab.py`

## 3. 저장 JSON 정책

저장되는 경기 JSON은 항상 최소 스키마(`schema_version = 2`)를 기준으로 합니다.

- 저장 JSON은 ingestion, validation, replay, structured correction에 필요한 필드만 유지합니다.
- Naver 응답 전체를 다시 저장하는 방향으로 확장하지 않습니다.
- 오래된 스키마 JSON은 로드 시점에 메모리에서 정규화할 수 있지만, 저장은 v2를 기준으로 합니다.

최소 스키마의 핵심 상위 필드는 다음과 같습니다.

- `schema_version`
- `game_id`
- `game_source`
- `collected_at`
- `lineup`
- `relay`
- `record`

세부 필드 정책은 코드 기준으로 추적합니다.

- `src/kbo_ingest/game_json.py`
- `src/kbo_ingest/game_validation.py`
- `src/kbo_ingest/normalize_game.py`
- `src/kbo_ingest/pa_scoring.py`
- `src/kbo_ingest/source_profile.py`

## 4. 보정과 자동 재구성 규칙

이 프로젝트의 보정은 JSON 텍스트를 직접 만지는 작업이 아니라, 경기 의미를 유지한 상태 재구성 작업입니다.

보정/정규화 로직을 바꿀 때 반드시 유지해야 하는 재구성 대상은 다음과 같습니다.

- `seqno`
- `currentGameState`
- 볼/스트라이크/아웃
- 주자 점유 상태
- 점수/안타/볼넷/실책 누계
- 타석 경계
- `record.batter`
- `record.pitcher`

에디터 저장 안전성도 유지해야 합니다.

- 저장 전 `.history/<game_stem>/` 아래에 `.bak`, `.patch`, `changes.jsonl`을 남깁니다.
- 자동 보정은 이후 이벤트 상태를 함께 다시 계산해야 합니다.

## 5. GUI 구조 원칙

GUI는 파일 수를 줄이되 책임 경계는 유지하는 방향으로 정리되어 있습니다.

- `kbo_integrated_gui.py`는 얇은 진입점만 담당하고 실제 시작은 `gui.app_shell.run()`에서 수행합니다.
- 탭 클래스는 UI 조정과 이벤트 연결에 집중합니다.
- 오래 걸리는 작업은 공용 `JobRunner`를 통해 UI 스레드 밖에서 실행합니다.
- 상태는 `gui.state.py`에 모아 두고, 탭 호환용 재수출 파일은 제거했습니다.
- 리플레이는 저장소 접근, 상태 계산, 네비게이션, 이상 탐지, 렌더링을 분리합니다.

## 6. 주요 워크플로

### 6.1 GUI 실행

```bash
python kbo_integrated_gui.py
```

탭별 역할은 다음과 같습니다.

- `Collection`: Naver 경기 JSON 수집
- `Correction Editor`: `lineup / relay / record` 구조화 보정, 검증, 백업 포함 저장
- `Ingestion`: manifest 생성, schema 생성, DB 적재, 검증 실행
- `Replay`: PostgreSQL의 정규화 결과를 불러와 상태를 재생하고 이상 탐지 확인

### 6.1.1 Collection 결과 분류

Collection 탭은 수집 결과를 아래 네 가지로 분리해서 다룹니다.

- `success`: `validate_game()`을 통과한 정상 수집본이다. `<save_dir>/<year>/<game_id>.json`에 저장한다.
- `anomaly`: `lineup / relay / record` 수집과 최소 스키마 JSON 생성은 되었지만 `validate_game()` 이슈 또는 validation 예외가 발생한 경우다. `<save_dir>/_anomalies/<year>/<game_id>.json`에 저장하고 `<save_dir>/logs/collection_anomalies_<timestamp>.jsonl`에 structured log를 남긴다.
- `failed`: 네트워크 오류, 응답 누락, 파싱 실패, 재시도 초과 등으로 정상 JSON을 만들지 못한 경우다. `<save_dir>/logs/collection_failures_<timestamp>.jsonl`에 기록하며, `Retry failed` 대상은 여기에만 포함한다.
- `skipped`: 정상 저장 경로에 이미 있고 다시 검증해도 `validate_game()`을 통과하는 파일을 재사용한 경우다.

anomaly 저장본도 정상 저장본과 동일하게 최소 스키마 JSON만 유지하며, Naver 원본 응답 전체를 따로 저장하지 않습니다.

### 6.1.2 Correction Editor 기본 흐름

수정/보정 UI는 "JSON 자유 편집기"가 아니라 "구조화 보정 도구"를 목표로 한다.

- 좌측 패널: 게임 파일 목록과 검증 문제 목록을 함께 본다.
- 중앙 패널: 선택 이벤트의 이닝/초말, 타석 범위, 앞뒤 문맥을 확인한다.
- 우측 패널: 현재 선택에 맞는 구조화 액션만 노출한다.

권장 순서는 다음과 같다.

1. 좌측에서 파일을 불러오고 문제 목록에서 수정할 항목을 선택한다.
2. 중앙에서 선택 이벤트와 타석 문맥을 확인한다.
3. 우측 기본 모드에서 `이벤트 추가`, `결과 의미 수정`, `타석 분리 / 병합`, `자동 재계산 미리보기` 중 알맞은 액션을 적용한다.
4. 검증 변화와 미리보기를 확인한 뒤 저장한다.

Correction Editor의 중계 구조화 편집 액션과 `자동 재계산 미리보기` / `자동 재계산 적용`은 기본적으로 `relay`와 이벤트 `currentGameState` 재구성에만 사용하고, `record.batter` / `record.pitcher`는 자동으로 덮어쓰지 않는다. 에디터에서는 중계에서 계산한 결과와 기록 탭 값을 비교할 수 있어야 하므로, 기록 수정은 별도 액션으로 유지한다.

자동 재계산은 타격 결과 뒤에 이어지는 `홈인` / `진루` / `아웃` 주자 이벤트를 같은 플레이의 후속 설명으로 해석한다. 따라서 이미 기본 진루 계산으로 반영된 주자를 후속 이벤트가 다시 참조하더라도, 같은 주자의 득점이나 아웃을 중복 집계하지 않도록 러너 식별자를 기준으로 한 번만 적용한다.

중계를 바로잡은 뒤 validation의 `relay vs record` 불일치를 해소하려면 명시적으로 `relay 기준 기록 동기화` 또는 `자동 재계산 + 기록 동기화`를 실행한다. 이 액션은 relay를 다시 계산한 뒤 그 결과를 기준으로 `record.batter` / `record.pitcher` / 타자 합계를 다시 쓴다.

검증 결과에 `partial_plate_appearance` 경고가 보이면, 릴레이 안에 타석 결과가 없는 부분 타석이 남아 있다는 뜻이다. 이런 경우에는 단순히 기존 merged 경고만 정리해도 `relay vs record` 불일치가 남을 수 있으므로, 해당 위치에서 타석 분리/결과 보정/누락 이벤트 추가를 함께 확인해야 한다.

검증 결과에 `missing_pitch_event` 오류가 보이면, 같은 타석 안에서 `pitchNum`이 1부터 시작하지 않거나 중간 번호가 비어 있다는 뜻이다. 예를 들어 `1 -> 3`처럼 번호가 점프하면 누락 투구로 보고, 해당 위치에서 빠진 투구 이벤트를 보정해야 한다.

`이벤트 추가`는 전체 필드를 직접 채우는 폼이 아니라, 선택 위치 기준 자동 채움 방식으로 사용한다.

- 사용자는 `선택 이벤트 앞 / 뒤`, `이벤트 종류`, 그리고 꼭 필요한 최소 입력만 고른다.
- `투구` 추가 시에는 보통 `투구 결과`, `원본 pitch id(선택)`, 필요하면 문구만 입력한다.
- `타격 결과` 추가 시에는 `결과 유형`, 필요하면 `결과 문구`와 `주자 이동`만 입력한다. 이때 결과 이벤트에는 `pitchNum` / `pitchResult` / `ptsPitchId`를 저장하지 않는다.
- `batter_id`, `batter_name`, `pitcher_id`, `seqno`, `pitch_num`, `currentGameState` 연결은 현재 선택 문맥을 기준으로 자동 후보를 계산하고, 저장 전 자동 재계산과 검증으로 다시 확인한다.

좌측 검증 문제 목록에서 항목을 선택하면 전체 설명이 목록 아래 상세 박스와 `검증 결과` 탭에 함께 표시된다. 표 칸이 좁아도 선택한 항목의 전문을 그대로 확인할 수 있고, 문제 목록 표 자체도 가로 스크롤로 끝까지 확인할 수 있다.

`타석 분리`도 기본 모드와 고급 모드를 구분해서 사용한다.

- 기본 모드에서는 중앙 이벤트 목록에서 "새 타석이 시작되어야 하는 이벤트"를 고른 뒤, 공격 팀 엔트리에서 새 타자를 선택하고 적용한다.
- 기본 모드 분리는 선택 이벤트 앞쪽에 이전 타석 종료 이벤트가 이미 있어야만 허용한다.
- 기본 모드 분리는 선택 이벤트부터 현재 타석 끝까지를 새 릴레이 블록으로 떼어 내고, 좌측 블록 목록에서도 새 타석이 별도 블록으로 보이게 정리한다.
- 선택 이벤트가 이미 새 타석 시작으로 추정되더라도 intro 이벤트가 없는 경우에는 기본 모드에서 intro 보강과 새 블록 분리로 안전하게 정리할 수 있다.
- 필요하면 새 타석 intro 이벤트를 자동 삽입하고, 선택 이벤트부터 현재 세그먼트를 새 타자 타석으로 재귀속한 뒤 자동 재계산으로 상태를 다시 만든다. 기록 탭 값은 별도 비교 대상으로 유지한다.
- 양쪽 타석 결과를 직접 다시 정의해야 하는 복잡한 경우에는 고급 모드의 상세 분리를 사용한다.

고급 모드는 raw 이벤트, game info, lineup, record를 직접 확인하거나 수정해야 할 때만 사용한다.

### 6.2 최소 스키마 마이그레이션

드라이런:

```bash
python -m scripts.migrate_game_json games
```

백업과 패치를 남기며 제자리 갱신:

```bash
python -m scripts.migrate_game_json games --in-place
```

다른 디렉터리로 출력:

```bash
python -m scripts.migrate_game_json games --output-dir migrated_games
```

### 6.3 JSON 검증

```bash
python -m scripts.validate_game_json games
```

검증은 보조 도구가 아니라 제품 기능입니다.

- 깨진 데이터를 통과시키기 위해 규칙을 느슨하게 만들지 않습니다.
- 소스 문제와 로더/스키마 문제는 분리해서 봅니다.
- 다만 병살타/삼중살처럼 경기 의미상 한 이벤트에서 아웃이 2개 이상 늘어나는 경우는 정상 흐름으로 보고 별도 `state_jump` 경고를 만들지 않습니다.

### 6.4 PostgreSQL 적재와 검증

manifest 생성:

```bash
python -m scripts.postgres_loader manifest --data-dir games --seasons 2024 2025 --seed 20260404 --output reports/manifests/kbo_2024_2025_seed20260404.json
```

manifest 적재:

```bash
python -m scripts.postgres_loader load --dsn "<DSN>" --schema sql/schema.sql --manifest reports/manifests/kbo_2024_2025_seed20260404.json --report-json reports/stage_loads/load_report.json
```

전체 적재 후 대량 검증:

```bash
python -m scripts.bulk_validate_full --dsn "<DSN>" --manifest reports/manifests/kbo_2024_2025_seed20260404.json --report-json reports/final_run/full_validate_report.json
```

적재 시 지켜야 할 데이터 규칙은 다음과 같습니다.

- `ptsPitchId`는 전역 고유값이 아니므로 정규화된 `pitches.pitch_id`는 경기 단위로 namespacing 합니다.
- 원본 raw pitch id는 별도 필드로 보존합니다.
- 중복으로 들어온 raw tracking 행은 조용히 제거하지 않습니다.
- 종료 결과가 없는 부분 타석도 모델링합니다.

## 7. 검증과 테스트 실행

변경 범위에 맞는 최소 검증부터 실행합니다.

JSON/보정/스키마 변경 시:

```bash
python -m scripts.validate_game_json games
python -m scripts.migrate_game_json games
```

GUI/리플레이 변경 시:

```bash
pytest tests/test_gui_job_runner.py tests/test_gui_layout_manager.py tests/test_replay_refactor.py
```

보정기나 수집기까지 건드렸다면 다음 테스트도 우선 후보입니다.

```bash
pytest tests/test_editor_tab.py tests/test_editor_core.py tests/test_naver_scraper.py
```

## 8. 이번 단순화 리팩터링에서 정리한 것

이번 정리에서는 “파일 수를 줄이되 책임 경계는 보존한다”를 기준으로 다음을 수행했습니다.

- 공용 작업 타입을 `gui/jobs/job_runner.py`로 합쳐 `gui/jobs/task_state.py`를 제거
- 탭 레지스트리 정의를 `gui/tabs/__init__.py`로 합쳐 얇은 중간 파일 제거
- `tabs/shared_state.py` 같은 호환용 재수출 파일 제거
- 사용되지 않던 `gui/components/modal.py` 제거
- 실험 성격이 강하고 핵심 워크플로에서 벗어난 스크립트 정리
- 문서를 이 가이드 하나로 통합하고 `README.md`는 진입점만 남기도록 축소
- 스크래퍼 기본 이름은 `NaverScraper`만 사용하고, 래퍼/별칭 없이 직접 참조

## 9. 유지 보수 원칙

- 단순함이 추상화보다 우선입니다.
- 파일 수를 늘리는 얇은 래퍼보다, 책임이 분명한 모듈을 선호합니다.
- 데이터 정확성과 검증 강도를 편의성보다 우선합니다.
- GUI는 항상 반응성을 유지해야 하며, 무거운 작업은 UI 스레드 밖으로 보냅니다.
- 문서는 한국어를 기본으로 하며, 이 가이드를 우선 갱신합니다.

## 10. 계층 분리 원칙

현재 저장소는 다음 경계를 기준으로 기능을 추가합니다.

- `gui/`, `tabs/`
  - DearPyGui 위젯 생성
  - 사용자 입력 수집
  - 버튼/탭 이벤트 연결
  - 진행률, 로그, 경고, 요약 표시
- `services/`
  - GUI에서 받은 요청 DTO 처리
  - scraper / repository / validator / core 로직 조합
  - 결과 DTO 반환
- `core/`
  - replay 상태 계산
  - 내비게이션 모델 구성
  - 이상 징후 탐지
  - GUI/DB와 무관한 순수 규칙
- `infrastructure/`
  - Naver 수집기
  - JSON 파일 저장과 로그 기록
  - PostgreSQL 연결과 조회

의존 방향은 `gui -> services -> core / infrastructure`를 기본으로 합니다.

- `services`는 `gui`를 import 하지 않습니다.
- `core`는 `DearPyGui`, `psycopg`, 파일 저장 로직에 의존하지 않습니다.
- `kbo_integrated_gui.py`는 얇은 진입점만 유지하고 실제 시작은 `gui.app_shell.run()`에서 담당합니다.

현재 반영된 대표 흐름은 다음과 같습니다.

- 수집: `tabs/collection_tab.py` -> `services/collection_service.py` -> `infrastructure/naver_scraper.py`, `infrastructure/json_repository.py`
- 적재: `tabs/ingestion_tab.py` -> `services/ingestion_service.py` -> `src/kbo_ingest/*`, `infrastructure/postgres_repository.py`
- replay: `tabs/replay_tab.py` -> `services/replay_service.py` -> `core/replay/*`, `infrastructure/postgres_repository.py`

`tabs/editor_tab.py`는 이미 `src/kbo_ingest.editor_core`, `src/kbo_ingest.correction_engine`를 적극적으로 사용하지만, 파일 탐색과 세션 로딩까지 완전히 서비스 계층으로 분리하는 작업은 후속 기술부채로 남아 있습니다.
