# naver_KBO_relay_scraping

Scrape KBO relay data from Naver with Selenium.

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

### 통합 GUI 실행 (탭형: 수집/적재/Replay)

`kbo_integrated_gui.py`에서 하나의 GUI에서 아래 기능을 탭으로 실행할 수 있습니다.

- 데이터 수집 탭: 수집 GUI 실행
- 데이터 적재 탭: DSN 연결, 스키마 생성, JSON 적재
- Replay/검증 탭: 게임 로드, 리플레이 확인, 경고 재검사

```bash
python kbo_integrated_gui.py
```

### 생성/사용 테이블

- `raw_games`: 원본 JSON 저장
- `teams`, `players`, `games`: 기본 차원 정보
- `events`: 이벤트 본문(이전/다음 이벤트 링크 포함)
- `event_links`: 이벤트 관계(`NEXT`)

`events`에는 `prev_event_id`, `next_event_id`, `seq_no`가 함께 저장되어,
이벤트 체인 탐색과 분석 집계(정렬 기반)를 모두 지원합니다.
