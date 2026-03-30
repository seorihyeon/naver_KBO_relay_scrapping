# KBO Relay DB 설계 (Raw + Normalized 2계층)

## 왜 2계층이 필요한가
- `relay`는 UI 블록(`title`, `titleStyle`)과 실제 플레이 이벤트(`textOptions`)가 섞여 있어, 블록 단위를 그대로 타석으로 매핑하면 오분류가 발생한다.
- 규칙이 바뀌거나 분류 로직이 개선될 때 재처리를 위해 원본 JSON을 손실 없이 보존해야 한다.
- 따라서 **raw 보존 계층**(`raw_games`, `raw_relay_blocks`, `raw_text_events`, `raw_pitch_tracks`, `raw_plate_metrics`)과 **정규화 계층**(`innings`, `plate_appearances`, `pa_events`, `pitches`, `pitch_tracking` 등)을 분리한다.

## 관계 개요
1. `raw_games` <- 원본 파일 1개
2. `raw_relay_blocks` <- 게임 내 relay 블록
3. `raw_text_events` / `raw_pitch_tracks` <- 블록 내 이벤트/투구추적
4. 정규화 시 `games`/`game_roster_entries` + `innings` + `plate_appearances` + `pa_events` 생성
5. `ptsPitchId = pitchId`로 `pitches`와 `pitch_tracking` 연결
6. `pa_events`에서 파생하여 `baserunning_events`, `review_events`, `substitution_events` 생성

## 타석 재구성 규칙
- 입력: `raw_text_events`를 `seqno` 기준 정렬.
- 반이닝 키: `(inning_no, half)`.
- 새 타석 시작 조건:
  - 현재 타석이 없음
  - batter가 변경됨
- 타석 종료 조건:
  - 타자 결과 텍스트/분류(`bat_result`) 감지
  - 아웃/볼넷/삼진/사구 등 종료 키워드 감지
- 투수교체는 타석을 강제 종료하지 않고 `substitution_events`에 기록.

## 이벤트 분류 기준
- `pitch`: `pitchNum` 또는 `pitchResult` 또는 `ptsPitchId` 존재
- `substitution`: `playerChange` 존재
- `review`: 텍스트에 `비디오 판독`
- `baserunning`: `주자/도루/진루/아웃/홈인/견제` 키워드
- `bat_result`: `안타/홈런/삼진/뜬공/땅볼/볼넷/사구/병살`
- 그 외 `other`

## 구현 파일
- DDL: `sql/schema.sql`
- Raw 적재: `src/kbo_ingest/ingest_raw.py`
- 정규화/타석 재구성: `src/kbo_ingest/normalize_game.py`
- 파이프라인/검증: `src/kbo_ingest/pipeline.py`
