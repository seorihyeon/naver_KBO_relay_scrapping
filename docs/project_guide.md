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
- `check_data.py`: 최소 스키마 기반 검증
- `migrate_game_json.py`: 저장 JSON을 최소 스키마로 마이그레이션
- `postgres_loader.py`: manifest 생성, DB 적재, 검증, sample-loop 실행
- `src/kbo_ingest/`: 스키마 최소화, 보정, 정규화, 적재, 검증의 핵심 도메인 로직
- `tabs/`: GUI 탭 컨트롤러
- `gui/`: 앱 셸, 상태, 공용 작업 인프라, 재사용 컴포넌트, 리플레이 보조 로직
- `sql/schema.sql`: PostgreSQL 스키마
- `tests/`: GUI 순수 로직, 정규화, 보정, 적재 관련 테스트

도메인 경계는 아래처럼 유지합니다.

- 수집: `web_interface.py`, `gui/collection_service.py`, `tabs/collection_tab.py`
- 보정/에디터: `src/kbo_ingest/editor_core.py`, `src/kbo_ingest/correction_engine.py`, `tabs/editor_tab.py`
- 적재: `src/kbo_ingest/ingest_raw.py`, `src/kbo_ingest/normalize_game.py`, `src/kbo_ingest/pipeline.py`, `postgres_loader.py`
- 검증/리플레이: `check_data.py`, `src/kbo_ingest/validation.py`, `gui/replay/*`, `tabs/replay_tab.py`

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
- `check_data.py`
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

### 6.1.1 Correction Editor 기본 흐름

수정/보정 UI는 "JSON 자유 편집기"가 아니라 "구조화 보정 도구"를 목표로 한다.

- 좌측 패널: 게임 파일 목록과 검증 문제 목록을 함께 본다.
- 중앙 패널: 선택 이벤트의 이닝/초말, 타석 범위, 앞뒤 문맥을 확인한다.
- 우측 패널: 현재 선택에 맞는 구조화 액션만 노출한다.

권장 순서는 다음과 같다.

1. 좌측에서 파일을 불러오고 문제 목록에서 수정할 항목을 선택한다.
2. 중앙에서 선택 이벤트와 타석 문맥을 확인한다.
3. 우측 기본 모드에서 `이벤트 추가`, `누락 타석 복구`, `결과 의미 수정`, `타석 분리 / 병합`, `자동 재계산 미리보기` 중 알맞은 액션을 적용한다.
4. 검증 변화와 미리보기를 확인한 뒤 저장한다.

`이벤트 추가`는 전체 필드를 직접 채우는 폼이 아니라, 선택 위치 기준 자동 채움 방식으로 사용한다.

- 사용자는 `선택 이벤트 앞 / 뒤`, `이벤트 종류`, 그리고 꼭 필요한 최소 입력만 고른다.
- `투구` 추가 시에는 보통 `투구 결과`, `원본 pitch id(선택)`, 필요하면 문구만 입력한다.
- `타격 결과` 추가 시에는 `결과 유형`, 필요하면 `결과 문구`와 `주자 이동`만 입력한다.
- `batter_id`, `batter_name`, `pitcher_id`, `seqno`, `pitch_num`, `currentGameState` 연결은 현재 선택 문맥을 기준으로 자동 후보를 계산하고, 저장 전 자동 재계산과 검증으로 다시 확인한다.

고급 모드는 raw 이벤트, game info, lineup, record를 직접 확인하거나 수정해야 할 때만 사용한다.

### 6.2 최소 스키마 마이그레이션

드라이런:

```bash
python migrate_game_json.py games
```

백업과 패치를 남기며 제자리 갱신:

```bash
python migrate_game_json.py games --in-place
```

다른 디렉터리로 출력:

```bash
python migrate_game_json.py games --output-dir migrated_games
```

### 6.3 JSON 검증

```bash
python check_data.py games
```

검증은 보조 도구가 아니라 제품 기능입니다.

- 깨진 데이터를 통과시키기 위해 규칙을 느슨하게 만들지 않습니다.
- 소스 문제와 로더/스키마 문제는 분리해서 봅니다.

### 6.4 PostgreSQL 적재와 검증

manifest 생성:

```bash
python postgres_loader.py manifest --data-dir games --seasons 2024 2025 --seed 20260404 --output reports/manifests/kbo_2024_2025_seed20260404.json
```

manifest 적재:

```bash
python postgres_loader.py load --dsn "<DSN>" --schema sql/schema.sql --manifest reports/manifests/kbo_2024_2025_seed20260404.json --report-json reports/stage_loads/load_report.json
```

전체 적재 후 대량 검증:

```bash
python scripts/bulk_validate_full.py --dsn "<DSN>" --manifest reports/manifests/kbo_2024_2025_seed20260404.json --report-json reports/final_run/full_validate_report.json
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
python check_data.py games
python migrate_game_json.py games
```

GUI/리플레이 변경 시:

```bash
pytest tests/test_gui_job_runner.py tests/test_gui_layout_manager.py tests/test_replay_refactor.py
```

보정기나 수집기까지 건드렸다면 다음 테스트도 우선 후보입니다.

```bash
pytest tests/test_editor_tab.py tests/test_editor_core.py tests/test_web_interface.py
```

## 8. 이번 단순화 리팩터링에서 정리한 것

이번 정리에서는 “파일 수를 줄이되 책임 경계는 보존한다”를 기준으로 다음을 수행했습니다.

- 공용 작업 타입을 `gui/jobs/job_runner.py`로 합쳐 `gui/jobs/task_state.py`를 제거
- 탭 레지스트리 정의를 `gui/tabs/__init__.py`로 합쳐 얇은 중간 파일 제거
- `tabs/shared_state.py` 같은 호환용 재수출 파일 제거
- 사용되지 않던 `gui/components/modal.py` 제거
- 실험 성격이 강하고 핵심 워크플로에서 벗어난 스크립트 정리
- 문서를 이 가이드 하나로 통합하고 `README.md`는 진입점만 남기도록 축소
- 스크래퍼 기본 이름을 `NaverScraper`로 명확화하고 기존 `Scrapper`는 호환 별칭으로만 유지

## 9. 유지 보수 원칙

- 단순함이 추상화보다 우선입니다.
- 파일 수를 늘리는 얇은 래퍼보다, 책임이 분명한 모듈을 선호합니다.
- 데이터 정확성과 검증 강도를 편의성보다 우선합니다.
- GUI는 항상 반응성을 유지해야 하며, 무거운 작업은 UI 스레드 밖으로 보냅니다.
- 문서는 한국어를 기본으로 하며, 이 가이드를 우선 갱신합니다.
