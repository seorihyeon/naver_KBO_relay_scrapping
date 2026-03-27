
import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from common_utils import to_int


def ip_str_to_outs(ip: Any) -> int:
    """
    네이버 투수 이닝 문자열 -> 아웃 수 변환.

    예:
    - '6'   -> 18
    - '6.2' -> 20
    - '0 ⅓' -> 1
    - '1 ⅔' -> 5
    """
    if ip in (None, "", "-", " "):
        return 0

    s = str(ip).strip()

    if "⅓" in s or "⅔" in s:
        whole = 0
        match = re.match(r"(\d+)", s)
        if match:
            whole = int(match.group(1))
        return whole * 3 + (1 if "⅓" in s else 2)

    if "." in s:
        whole, frac = s.split(".", 1)
        return to_int(whole) * 3 + to_int(frac)

    return to_int(s) * 3


def extract_lineup_players(lineup: Dict[str, Any]) -> Dict[str, Any]:
    """lineup 블록에서 팀별 선수 구성을 정리한다."""
    result = {
        "game_info": lineup.get("game_info", {}),
        "home": {
            "starter_pitcher": None,
            "starter_batters": {},
            "bullpen": {},
            "candidates": {},
        },
        "away": {
            "starter_pitcher": None,
            "starter_batters": {},
            "bullpen": {},
            "candidates": {},
        },
    }

    for side in ("home", "away"):
        starters = lineup.get(f"{side}_starter") or []
        bullpen = lineup.get(f"{side}_bullpen") or []
        candidates = lineup.get(f"{side}_candidate") or []

        for player in starters:
            pcode = str(player.get("playerCode") or "")
            if not pcode:
                continue

            position = str(player.get("position") or "")
            if position == "1":
                result[side]["starter_pitcher"] = pcode
            else:
                result[side]["starter_batters"][pcode] = {
                    "name": player.get("playerName", ""),
                    "batorder": to_int(player.get("batorder")),
                    "position": position,
                    "positionName": player.get("positionName", ""),
                }

        for player in bullpen:
            pcode = str(player.get("playerCode") or "")
            if pcode:
                result[side]["bullpen"][pcode] = player.get("playerName", "")

        for player in candidates:
            pcode = str(player.get("playerCode") or "")
            if pcode:
                result[side]["candidates"][pcode] = player.get("playerName", "")

    return result


def extract_record_batters(batter_block: Dict[str, Any]) -> Dict[str, Any]:
    """record['batter']를 팀/선수별 dict로 정리한다."""
    result = {
        "home": {},
        "away": {},
        "homeTotal": batter_block.get("homeTotal", {}),
        "awayTotal": batter_block.get("awayTotal", {}),
    }

    for side in ("home", "away"):
        for row in batter_block.get(side, []) or []:
            pcode = str(row.get("playerCode") or "")
            if not pcode:
                continue

            result[side][pcode] = {
                "name": row.get("name", ""),
                "batOrder": to_int(row.get("batOrder")),
                "ab": to_int(row.get("ab")),
                "hit": to_int(row.get("hit")),
                "bb": to_int(row.get("bb")),
                "hr": to_int(row.get("hr")),
                "rbi": to_int(row.get("rbi")),
                "so": to_int(row.get("kk")),
                "run": to_int(row.get("run")),
                "sb": to_int(row.get("sb")),
            }

    return result


def extract_record_pitchers(pitcher_block: Dict[str, Any]) -> Dict[str, Any]:
    """record['pitcher']를 팀/선수별 dict로 정리한다."""
    result = {"home": {}, "away": {}}

    for side in ("home", "away"):
        for row in pitcher_block.get(side, []) or []:
            pcode = str(row.get("pcode") or "")
            if not pcode:
                continue

            result[side][pcode] = {
                "name": row.get("name", ""),
                "outs": ip_str_to_outs(row.get("inn")),
                "inn_raw": row.get("inn"),
                "r": to_int(row.get("r")),
                "er": to_int(row.get("er")),
                "hit": to_int(row.get("hit")),
                "bb": to_int(row.get("bb")),
                "kk": to_int(row.get("kk")),
                "hr": to_int(row.get("hr")),
                "ab": to_int(row.get("ab")),
                "bf": to_int(row.get("bf")),
                "pa": to_int(row.get("pa")),
                "bbhp": to_int(row.get("bbhp")),
            }

    return result


def classify_pa_text(text: str) -> Dict[str, int]:
    """
    중계 text(type 13/23 기준)에서 타석 결과를 단순 분류한다.
    """
    text = text or ""

    is_hbp = "몸에 맞는 볼" in text
    is_walk = any(keyword in text for keyword in ("볼넷", "고의4구", "고의 4구")) and not is_hbp
    is_hit = any(keyword in text for keyword in ("안타", "1루타", "2루타", "3루타", "홈런"))
    is_sac = ("희생플라이" in text) or ("희생번트" in text)
    is_so = ("삼진 아웃" in text) or ("스트라이크 낫 아웃" in text) or ("스트라이크 낫아웃" in text)

    pa = 1
    ab = hit = bb = so = hbp = 0

    if is_walk:
        bb = 1
    elif is_hbp:
        hbp = 1
    elif is_hit:
        ab = 1
        hit = 1
    else:
        if not is_sac:
            ab = 1
        if is_so:
            so = 1

    return {
        "pa": pa,
        "ab": ab,
        "hit": hit,
        "bb": bb,
        "so": so,
        "hbp": hbp,
    }


def build_batter_stats_from_relay(relay: List[List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    relay에서 type 13/23 이벤트만 사용해 타자별 간이 스탯을 집계한다.
    """
    result: Dict[str, Dict[str, Dict[str, int]]] = {"home": {}, "away": {}}

    def get_bucket(side: str, pcode: str) -> Dict[str, int]:
        if pcode not in result[side]:
            result[side][pcode] = {"pa": 0, "ab": 0, "hit": 0, "bb": 0, "so": 0, "hbp": 0}
        return result[side][pcode]

    for inning in relay:
        for half in inning:
            offense_side = "away" if str(half.get("homeOrAway")) == "0" else "home"

            for text_option in half.get("textOptions") or []:
                if text_option.get("type") not in (13, 23):
                    continue

                cgs = text_option.get("currentGameState") or {}
                batter = str(cgs.get("batter") or "")
                if not batter:
                    continue

                delta = classify_pa_text(text_option.get("text") or "")
                bucket = get_bucket(offense_side, batter)

                for key, value in delta.items():
                    bucket[key] += value

    return result


def collect_pitcher_codes_from_relay(relay: List[List[Dict[str, Any]]]) -> Dict[str, set]:
    """
    relay의 currentGameState.pitcher를 기준으로 실제 등판한 투수 코드를 수집한다.
    """
    result = {"home": set(), "away": set()}

    for inning in relay:
        for half in inning:
            defensive_side = "home" if str(half.get("homeOrAway")) == "0" else "away"

            for text_option in half.get("textOptions") or []:
                cgs = text_option.get("currentGameState") or {}
                pitcher = str(cgs.get("pitcher") or "")
                if pitcher:
                    result[defensive_side].add(pitcher)

    return result


def get_final_scoreboard_from_relay(relay: List[List[Dict[str, Any]]]) -> Dict[str, int] | None:
    """
    relay 마지막 이벤트의 currentGameState에서 최종 스코어보드를 추출한다.
    """
    last_event = None

    for inning in reversed(relay):
        for half in reversed(inning):
            texts = half.get("textOptions") or []
            if texts:
                last_event = texts[-1]
                break
        if last_event:
            break

    if not last_event:
        return None

    cgs = last_event.get("currentGameState") or {}
    if not cgs:
        return None

    return {
        "homeScore": to_int(cgs.get("homeScore")),
        "awayScore": to_int(cgs.get("awayScore")),
        "homeHit": to_int(cgs.get("homeHit")),
        "awayHit": to_int(cgs.get("awayHit")),
        "homeBallFour": to_int(cgs.get("homeBallFour")),
        "awayBallFour": to_int(cgs.get("awayBallFour")),
        "homeError": to_int(cgs.get("homeError")),
        "awayError": to_int(cgs.get("awayError")),
    }


def check_basic_shape(game: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []

    for key in ("lineup", "relay", "record"):
        if key not in game:
            issues.append(f"top-level key 누락: {key}")

    if issues:
        return issues, warnings

    lineup = game.get("lineup", {})

    for side in ("home", "away"):
        starters = lineup.get(f"{side}_starter") or []
        pitcher_count = sum(1 for p in starters if str(p.get("position")) == "1")
        batter_orders = sorted(
            to_int(p.get("batorder"))
            for p in starters
            if str(p.get("position")) != "1"
        )

        if pitcher_count != 1:
            issues.append(f"[{side}] starter 투수 수가 1이 아님: {pitcher_count}")

        if len(batter_orders) != 9:
            issues.append(f"[{side}] 선발 타자 수가 9명이 아님: {len(batter_orders)}")
        elif batter_orders != list(range(1, 10)):
            issues.append(f"[{side}] 선발 타순이 1~9가 아님: {batter_orders}")

    return issues, warnings


def check_game_info_vs_lineup(game_info: Dict[str, Any], lineup_info: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []

    home_starter = lineup_info["home"]["starter_pitcher"]
    away_starter = lineup_info["away"]["starter_pitcher"]

    if game_info.get("hPCode") and home_starter and str(game_info["hPCode"]) != str(home_starter):
        issues.append(
            f"[meta] game_info.hPCode({game_info['hPCode']}) != home 선발투수({home_starter})"
        )

    if game_info.get("aPCode") and away_starter and str(game_info["aPCode"]) != str(away_starter):
        issues.append(
            f"[meta] game_info.aPCode({game_info['aPCode']}) != away 선발투수({away_starter})"
        )

    return issues, warnings


def check_record_batter_team_totals(record_bats: Dict[str, Any]) -> List[str]:
    issues: List[str] = []

    for side in ("home", "away"):
        players = record_bats[side]
        total = record_bats[f"{side}Total"]

        for field in ("ab", "hit", "rbi", "run", "sb"):
            player_sum = sum(player[field] for player in players.values())
            total_value = to_int(total.get(field))
            if player_sum != total_value:
                issues.append(
                    f"[{side}] batter teamTotal.{field} 불일치: players={player_sum}, total={total_value}"
                )

    return issues


def check_batters_vs_scoreboard(record_bats: Dict[str, Any], scoreboard: Dict[str, int] | None) -> List[str]:
    issues: List[str] = []
    if not scoreboard:
        return issues

    if to_int(record_bats["homeTotal"].get("run")) != scoreboard["homeScore"]:
        issues.append(
            f"[score] home 득점 불일치: batter_total={record_bats['homeTotal'].get('run')}, scoreboard={scoreboard['homeScore']}"
        )

    if to_int(record_bats["awayTotal"].get("run")) != scoreboard["awayScore"]:
        issues.append(
            f"[score] away 득점 불일치: batter_total={record_bats['awayTotal'].get('run')}, scoreboard={scoreboard['awayScore']}"
        )

    if to_int(record_bats["homeTotal"].get("hit")) != scoreboard["homeHit"]:
        issues.append(
            f"[score] home 안타 불일치: batter_total={record_bats['homeTotal'].get('hit')}, scoreboard={scoreboard['homeHit']}"
        )

    if to_int(record_bats["awayTotal"].get("hit")) != scoreboard["awayHit"]:
        issues.append(
            f"[score] away 안타 불일치: batter_total={record_bats['awayTotal'].get('hit')}, scoreboard={scoreboard['awayHit']}"
        )

    return issues


def check_lineup_vs_record_batter(lineup_info: Dict[str, Any], record_bats: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []

    for side in ("home", "away"):
        starter_batters = lineup_info[side]["starter_batters"]
        candidates = lineup_info[side]["candidates"]

        known_batters = set(starter_batters.keys()) | set(candidates.keys())
        known_batters |= set(lineup_info[side]["bullpen"].keys())
        if lineup_info[side]["starter_pitcher"]:
            known_batters.add(lineup_info[side]["starter_pitcher"])

        record_batter_codes = set(record_bats[side].keys())

        extra_record = record_batter_codes - known_batters
        if extra_record:
            issues.append(
                f"[{side}] record.batter에 라인업/후보에 없는 타자 존재: {sorted(extra_record)}"
            )

        missing_record = set(starter_batters.keys()) - record_batter_codes
        if missing_record:
            warnings.append(
                f"[{side}] 선발 타자 중 record.batter에 없는 선수: {sorted(missing_record)}"
            )

        for pcode, starter in starter_batters.items():
            if pcode not in record_bats[side]:
                continue

            lineup_order = starter["batorder"]
            record_order = record_bats[side][pcode]["batOrder"]
            if lineup_order and record_order and lineup_order != record_order:
                warnings.append(
                    f"[{side}] 타순 불일치 {pcode} {starter['name']}: lineup={lineup_order}, record={record_order}"
                )

    return issues, warnings


def check_relay_vs_record_batter(relay_bats: Dict[str, Any], record_bats: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    relay(type 13/23 기반 간이 집계)와 record.batter를 비교한다.

    run만 기록된 대주자/대수비는 relay에 안 잡힐 수 있으므로,
    실제 타석 성적(ab/hit/bb/hr/rbi/so)이 있을 때만 누락으로 본다.
    """
    issues: List[str] = []
    warnings: List[str] = []

    for side in ("home", "away"):
        relay_codes = set(relay_bats[side].keys())
        record_codes = set(record_bats[side].keys())

        extra_relay = relay_codes - record_codes
        if extra_relay:
            issues.append(f"[{side}] relay에만 있는 타자: {sorted(extra_relay)}")

        missing_from_relay = []
        for pcode in sorted(record_codes - relay_codes):
            row = record_bats[side][pcode]
            if any(row[key] for key in ("ab", "hit", "bb", "hr", "rbi", "so")):
                missing_from_relay.append(pcode)

        if missing_from_relay:
            issues.append(
                f"[{side}] record에는 있는데 relay에 없는 타자: {missing_from_relay}"
            )

        for pcode in sorted(relay_codes & record_codes):
            relay_row = relay_bats[side][pcode]
            record_row = record_bats[side][pcode]

            for record_field, relay_field in (("ab", "ab"), ("hit", "hit"), ("bb", "bb"), ("so", "so")):
                if relay_row[relay_field] != record_row[record_field]:
                    issues.append(
                        f"[{side}] 타자 {pcode} {record_row['name']} {record_field} 불일치: "
                        f"relay={relay_row[relay_field]}, record={record_row[record_field]}"
                    )

    return issues, warnings


def check_lineup_vs_record_pitcher(lineup_info: Dict[str, Any], record_pits: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    투수 검증은 '등판 가능한 로스터' 기준으로 본다.

    올스타전/특수 상황에서는 야수가 투수로 기록될 수 있으므로
    순수 투수 목록(선발/불펜)만 보지 않고 선발타자/후보까지 포함한다.
    """
    issues: List[str] = []
    warnings: List[str] = []

    for side in ("home", "away"):
        roster_codes = set(lineup_info[side]["bullpen"].keys())
        roster_codes |= set(lineup_info[side]["starter_batters"].keys())
        roster_codes |= set(lineup_info[side]["candidates"].keys())
        if lineup_info[side]["starter_pitcher"]:
            roster_codes.add(lineup_info[side]["starter_pitcher"])

        record_codes = set(record_pits[side].keys())
        extra_record = record_codes - roster_codes
        if extra_record:
            issues.append(
                f"[{side}] record.pitcher에 로스터(선발/후보/불펜)에 없는 선수 존재: {sorted(extra_record)}"
            )

    return issues, warnings


def check_relay_pitchers_vs_record_and_lineup(
    relay_pitchers: Dict[str, set],
    record_pits: Dict[str, Any],
    lineup_info: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []

    for side in ("home", "away"):
        roster_codes = set(lineup_info[side]["bullpen"].keys())
        roster_codes |= set(lineup_info[side]["starter_batters"].keys())
        roster_codes |= set(lineup_info[side]["candidates"].keys())
        if lineup_info[side]["starter_pitcher"]:
            roster_codes.add(lineup_info[side]["starter_pitcher"])

        relay_codes = relay_pitchers[side]
        record_codes = set(record_pits[side].keys())

        missing_relay = record_codes - relay_codes
        if missing_relay:
            issues.append(f"[{side}] record.pitcher에는 있는데 relay에 없는 투수: {sorted(missing_relay)}")

        extra_relay = relay_codes - record_codes
        if extra_relay:
            issues.append(f"[{side}] relay에는 있는데 record.pitcher에 없는 투수: {sorted(extra_relay)}")

        outside_roster = relay_codes - roster_codes
        if outside_roster:
            issues.append(f"[{side}] relay에 로스터 밖 투수 코드 존재: {sorted(outside_roster)}")

    return issues, warnings


def check_pitchers_vs_batters(record_pits: Dict[str, Any], record_bats: Dict[str, Any]) -> List[str]:
    issues: List[str] = []

    for side in ("home", "away"):
        opponent = "away" if side == "home" else "home"
        pits = record_pits[side]
        opp_total = record_bats[f"{opponent}Total"]
        opp_batters = record_bats[opponent]

        if sum(p["r"] for p in pits.values()) != to_int(opp_total.get("run")):
            issues.append(f"[{side}] 투수 r 합 != 상대 teamTotal.run")

        if sum(p["hit"] for p in pits.values()) != to_int(opp_total.get("hit")):
            issues.append(f"[{side}] 투수 hit 합 != 상대 teamTotal.hit")

        if sum(p["bb"] for p in pits.values()) != sum(b["bb"] for b in opp_batters.values()):
            issues.append(f"[{side}] 투수 bb 합 != 상대 타자 bb 합")

        if sum(p["hr"] for p in pits.values()) != sum(b["hr"] for b in opp_batters.values()):
            issues.append(f"[{side}] 투수 hr 합 != 상대 타자 hr 합")

        if sum(p["ab"] for p in pits.values()) != sum(b["ab"] for b in opp_batters.values()):
            issues.append(f"[{side}] 투수 ab 합 != 상대 타자 ab 합")

    return issues


def check_pitchers_vs_scoreboard(record_pits: Dict[str, Any], scoreboard: Dict[str, int] | None) -> List[str]:
    issues: List[str] = []
    if not scoreboard:
        return issues

    if sum(p["r"] for p in record_pits["away"].values()) != scoreboard["homeScore"]:
        issues.append("[score] away 투수 r 합 != homeScore")

    if sum(p["r"] for p in record_pits["home"].values()) != scoreboard["awayScore"]:
        issues.append("[score] home 투수 r 합 != awayScore")

    if sum(p["hit"] for p in record_pits["away"].values()) != scoreboard["homeHit"]:
        issues.append("[score] away 투수 hit 합 != homeHit")

    if sum(p["hit"] for p in record_pits["home"].values()) != scoreboard["awayHit"]:
        issues.append("[score] home 투수 hit 합 != awayHit")

    if sum(p["bbhp"] for p in record_pits["away"].values()) != scoreboard["homeBallFour"]:
        issues.append("[score] away 투수 bbhp 합 != homeBallFour")

    if sum(p["bbhp"] for p in record_pits["home"].values()) != scoreboard["awayBallFour"]:
        issues.append("[score] home 투수 bbhp 합 != awayBallFour")

    return issues


def validate_game(game: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    warnings: List[str] = []

    basic_issues, basic_warnings = check_basic_shape(game)
    issues.extend(basic_issues)
    warnings.extend(basic_warnings)

    if issues:
        return {"ok": False, "issues": issues, "warnings": warnings}

    lineup = game.get("lineup", {})
    relay = game.get("relay", [])
    record = game.get("record", {})

    lineup_info = extract_lineup_players(lineup)
    record_bats = extract_record_batters(record.get("batter", {}))
    record_pits = extract_record_pitchers(record.get("pitcher", {}))
    relay_bats = build_batter_stats_from_relay(relay)
    relay_pitchers = collect_pitcher_codes_from_relay(relay)
    scoreboard = get_final_scoreboard_from_relay(relay)
    game_info = lineup_info["game_info"]

    i, w = check_game_info_vs_lineup(game_info, lineup_info)
    issues.extend(i)
    warnings.extend(w)

    issues.extend(check_record_batter_team_totals(record_bats))
    issues.extend(check_batters_vs_scoreboard(record_bats, scoreboard))

    i, w = check_lineup_vs_record_batter(lineup_info, record_bats)
    issues.extend(i)
    warnings.extend(w)

    i, w = check_relay_vs_record_batter(relay_bats, record_bats)
    issues.extend(i)
    warnings.extend(w)

    i, w = check_lineup_vs_record_pitcher(lineup_info, record_pits)
    issues.extend(i)
    warnings.extend(w)

    i, w = check_relay_pitchers_vs_record_and_lineup(relay_pitchers, record_pits, lineup_info)
    issues.extend(i)
    warnings.extend(w)

    issues.extend(check_pitchers_vs_batters(record_pits, record_bats))
    issues.extend(check_pitchers_vs_scoreboard(record_pits, scoreboard))

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def validate_json_file(json_path: Path) -> Dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as f:
        game = json.load(f)

    result = validate_game(game)
    return {
        "file": str(json_path),
        **result,
    }


def collect_json_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Naver KBO relay JSON 검증기")
    parser.add_argument(
        "path",
        nargs="?",
        default="games",
        help="검사할 JSON 파일 또는 디렉터리 (기본값: games)",
    )
    args = parser.parse_args()

    target = Path(args.path)
    files = collect_json_files(target)

    if not files:
        print(f"검사할 JSON 파일이 없습니다: {target}")
        return 1

    total = len(files)
    ok_count = 0
    warning_count = 0
    fail_count = 0

    for json_file in files:
        result = validate_json_file(json_file)

        if result["ok"]:
            ok_count += 1
            if result["warnings"]:
                warning_count += 1
                print(f"⚠️  {result['file']}")
                for msg in result["warnings"]:
                    print(f"   - {msg}")
            else:
                print(f"✅ {result['file']}")
        else:
            fail_count += 1
            print(f"❌ {result['file']}")
            for msg in result["issues"]:
                print(f"   - {msg}")
            if result["warnings"]:
                print("   [warnings]")
                for msg in result["warnings"]:
                    print(f"   - {msg}")

    print()
    print(f"총 {total}개 파일 검사 완료")
    print(f"  - 정상: {ok_count}")
    print(f"  - 경고만 있음: {warning_count}")
    print(f"  - 실패: {fail_count}")

    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
