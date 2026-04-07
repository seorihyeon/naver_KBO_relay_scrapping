# KBO Scrapping Analysis

이 저장소는 Naver KBO 중계 JSON을 수집하고, 구조화된 GUI에서 소스 오류를 보정한 뒤, PostgreSQL 적재와 검증/리플레이까지 재현 가능하게 수행하는 프로젝트입니다.

운영 규칙과 워크플로는 [`docs/project_guide.md`](docs/project_guide.md) 한 문서에 정리되어 있습니다.

자주 쓰는 진입점:

```bash
python kbo_integrated_gui.py
python migrate_game_json.py games
python check_data.py games
```

저장 JSON은 최소 스키마 `schema_version = 2`를 유지하며, GUI 저장 시 `.history/<game_stem>/` 아래에 백업과 변경 이력이 함께 생성됩니다.
