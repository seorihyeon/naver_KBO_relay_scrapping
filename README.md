# naver_KBO_relay_scrapping

Scrap KBO relay from Naver with Selenium.

## PostgreSQL 적재 스크립트

웹에서 수집한 JSON(`games/**/*.json`)을 PostgreSQL로 적재하는 스크립트를 추가했습니다.

### 설치

```bash
pip install psycopg[binary]
```

### 실행

```bash
python postgres_loader.py \
  --dsn "postgresql://USER:PASSWORD@HOST:5432/DBNAME" \
  --data-dir games \
  --create-schema
```

### 통합 GUI 실행 (수집/적재/리플레이)

`db_replay_dpg_qa.py`에서 하나의 GUI에서 아래 기능을 실행할 수 있습니다.

- DSN/경로를 외부 설정 파일(`config/app_config.json`)에서 로드
- 스키마 생성
- JSON 디렉터리 적재
- 리플레이 QA
- 수집 GUI 실행 버튼 제공

```bash
python db_replay_dpg_qa.py
```

### 생성/사용 테이블

- `raw_games`: 원본 JSON 저장
- `teams`, `players`, `games`: 기본 차원 정보
- `events`: 이벤트 본문(이전/다음 이벤트 링크 포함)
- `event_links`: 이벤트 관계(`NEXT`)

`events`에는 `prev_event_id`, `next_event_id`, `seq_no`가 함께 저장되어,
이벤트 체인 탐색과 분석 집계(정렬 기반)를 모두 지원합니다.
