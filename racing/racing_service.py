import time
import json
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("RacingService")

# In-memory cache to avoid rate limits and keep responses snappy
_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  


def _get_cache(key: str) -> Optional[Any]:
    if key in _CACHE:
        item = _CACHE[key]
        if time.time() < item["expires"]:
            return item["data"]
        else:
            del _CACHE[key]
    return None


def _set_cache(key: str, data: Any, ttl: int = CACHE_TTL):
    _CACHE[key] = {
        "data": data,
        "expires": time.time() + ttl
    }


class RacingService:
    """
    Service to fetch live data for Formula 1 and MotoGP:
    Standings, Race Results, Qualifying, Sprint, and Free Practice.
    """

    # -------------------------------------------------------------
    # FORMULA 1
    # -------------------------------------------------------------
    @staticmethod
    async def get_f1_driver_standings() -> Optional[Dict[str, Any]]:
        cache_key = "f1_driver_standings"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.jolpi.ca/ergast/f1/current/driverstandings.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json()

            table = raw.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
            if not table:
                return None
            current_list = table[0]
            season = current_list.get("season", "2026")
            round_no = current_list.get("round", "1")

            drivers = []
            for item in current_list.get("DriverStandings", []):
                d_info = item.get("Driver", {})
                c_info = item.get("Constructors", [{}])[0]
                drivers.append({
                    "position": int(item.get("position", 0)),
                    "first_name": d_info.get("givenName", ""),
                    "last_name": d_info.get("familyName", ""),
                    "code": d_info.get("code") or d_info.get("familyName", "")[:3].upper(),
                    "nationality": d_info.get("nationality", ""),
                    "team": c_info.get("name", "Unknown"),
                    "points": item.get("points", "0"),
                    "wins": item.get("wins", "0"),
                    "number": d_info.get("permanentNumber") or item.get("position", "1"),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "STANDINGS",
                "category": "DRIVER STANDINGS",
                "season": season,
                "round": round_no,
                "title": f"FORMULA 1 WORLD CHAMPIONSHIP {season}",
                "subtitle": f"DRIVER STANDINGS • ROUND {round_no}",
                "items": drivers[:10],
                "all_items": drivers,
                "metric_header": "POINTS",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_driver_standings: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_f1_constructor_standings() -> Optional[Dict[str, Any]]:
        cache_key = "f1_constructor_standings"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json()

            table = raw.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
            if not table:
                return None
            current_list = table[0]
            season = current_list.get("season", "2026")
            round_no = current_list.get("round", "1")

            constructors = []
            for item in current_list.get("ConstructorStandings", []):
                c_info = item.get("Constructor", {})
                constructors.append({
                    "position": int(item.get("position", 0)),
                    "first_name": "",
                    "last_name": c_info.get("name", "").upper(),
                    "code": c_info.get("name", "")[:3].upper(),
                    "nationality": c_info.get("nationality", ""),
                    "team": c_info.get("name", "Unknown"),
                    "points": item.get("points", "0"),
                    "wins": item.get("wins", "0"),
                    "number": str(item.get("position", "1")),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "STANDINGS",
                "category": "CONSTRUCTOR STANDINGS",
                "season": season,
                "round": round_no,
                "title": f"FORMULA 1 WORLD CHAMPIONSHIP {season}",
                "subtitle": f"CONSTRUCTOR STANDINGS • ROUND {round_no}",
                "items": constructors[:10],
                "all_items": constructors,
                "metric_header": "POINTS",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_constructor_standings: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_f1_last_results() -> Optional[Dict[str, Any]]:
        cache_key = "f1_last_results"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json()

            races = raw.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if not races:
                return None
            race = races[0]
            race_name = race.get("raceName", "Grand Prix")
            season = race.get("season", "2026")
            circuit_name = race.get("Circuit", {}).get("circuitName", "")
            results_list = race.get("Results", [])

            items = []
            for item in results_list:
                d_info = item.get("Driver", {})
                c_info = item.get("Constructor", {})
                pos = int(item.get("position", 0))

                time_val = ""
                if "Time" in item and "time" in item["Time"]:
                    time_val = item["Time"]["time"]
                else:
                    time_val = item.get("status", "")

                items.append({
                    "position": pos,
                    "first_name": d_info.get("givenName", ""),
                    "last_name": d_info.get("familyName", ""),
                    "code": d_info.get("code") or d_info.get("familyName", "")[:3].upper(),
                    "nationality": d_info.get("nationality", ""),
                    "team": c_info.get("name", "Unknown"),
                    "points": item.get("points", "0"),
                    "time": time_val,
                    "number": d_info.get("permanentNumber") or str(pos),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "RACE",
                "category": "RACE RESULTS",
                "season": season,
                "race_name": race_name,
                "circuit": circuit_name,
                "title": f"FORMULA 1 {race_name.upper()} {season}",
                "subtitle": "RACE RESULTS",
                "items": items[:10],
                "all_items": items,
                "metric_header": "TIME / GAP",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_last_results: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_f1_qualifying_results() -> Optional[Dict[str, Any]]:
        cache_key = "f1_qualifying_results"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.jolpi.ca/ergast/f1/current/last/qualifying.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json()

            races = raw.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if not races:
                return None
            race = races[0]
            race_name = race.get("raceName", "Grand Prix")
            season = race.get("season", "2026")
            circuit_name = race.get("Circuit", {}).get("circuitName", "")
            quali_list = race.get("QualifyingResults", [])

            items = []
            for item in quali_list:
                d_info = item.get("Driver", {})
                c_info = item.get("Constructor", {})
                pos = int(item.get("position", 0))

                time_val = item.get("Q3") or item.get("Q2") or item.get("Q1") or "--:--.---"

                items.append({
                    "position": pos,
                    "first_name": d_info.get("givenName", ""),
                    "last_name": d_info.get("familyName", ""),
                    "code": d_info.get("code") or d_info.get("familyName", "")[:3].upper(),
                    "nationality": d_info.get("nationality", ""),
                    "team": c_info.get("name", "Unknown"),
                    "time": time_val,
                    "number": d_info.get("permanentNumber") or item.get("number", str(pos)),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "QUALIFYING",
                "category": "QUALIFYING RESULTS",
                "season": season,
                "race_name": race_name,
                "circuit": circuit_name,
                "title": f"FORMULA 1 {race_name.upper()} {season}",
                "subtitle": "QUALIFYING",
                "items": items[:10],
                "all_items": items,
                "metric_header": "TIME",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_qualifying_results: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_f1_sprint_results() -> Optional[Dict[str, Any]]:
        cache_key = "f1_sprint_results"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.jolpi.ca/ergast/f1/current/sprint.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json()

            races = raw.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if not races:
                return None
            race = races[-1]  # Latest sprint race
            race_name = race.get("raceName", "Grand Prix")
            season = race.get("season", "2026")
            circuit_name = race.get("Circuit", {}).get("circuitName", "")
            sprint_list = race.get("SprintResults", [])

            items = []
            for item in sprint_list:
                d_info = item.get("Driver", {})
                c_info = item.get("Constructor", {})
                pos = int(item.get("position", 0))

                time_val = ""
                if "Time" in item and "time" in item["Time"]:
                    time_val = item["Time"]["time"]
                else:
                    time_val = item.get("status", "")

                items.append({
                    "position": pos,
                    "first_name": d_info.get("givenName", ""),
                    "last_name": d_info.get("familyName", ""),
                    "code": d_info.get("code") or d_info.get("familyName", "")[:3].upper(),
                    "nationality": d_info.get("nationality", ""),
                    "team": c_info.get("name", "Unknown"),
                    "points": item.get("points", "0"),
                    "time": time_val,
                    "number": d_info.get("permanentNumber") or str(pos),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "SPRINT",
                "category": "SPRINT RACE RESULTS",
                "season": season,
                "race_name": race_name,
                "circuit": circuit_name,
                "title": f"FORMULA 1 {race_name.upper()} {season}",
                "subtitle": "SPRINT RACE",
                "items": items[:10],
                "all_items": items,
                "metric_header": "TIME / GAP",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_sprint_results: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_f1_practice_results() -> Optional[Dict[str, Any]]:
        cache_key = "f1_practice_results"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        try:
            # Fetch past practice session from OpenF1
            url = "https://api.openf1.org/v1/sessions?session_type=Practice"
            headers = {"User-Agent": "Mozilla/5.0"}
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    sessions = await resp.json()

            now = datetime.now(timezone.utc).isoformat()
            past = [
                s for s in sessions
                if s.get("date_end") and s["date_end"] < now and not s.get("is_cancelled") and s.get("session_name") in ["Practice 1", "Practice 2", "Practice 3"]
            ]
            if not past:
                return None
            last_s = past[-1]
            s_key = last_s["session_key"]
            session_name = last_s.get("session_name", "Practice 2").upper()
            location = last_s.get("location", "Grand Prix")

            # Fetch drivers
            d_url = f"https://api.openf1.org/v1/drivers?session_key={s_key}"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(d_url, headers=headers) as resp:
                    drivers = await resp.json()
            d_map = {d["driver_number"]: d for d in drivers}

            # Fetch laps
            l_url = f"https://api.openf1.org/v1/laps?session_key={s_key}"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(l_url, headers=headers) as resp:
                    laps = await resp.json()

            best = {}
            for l in laps:
                dn = l.get("driver_number")
                dur = l.get("lap_duration")
                if dur and dur > 40:
                    if dn not in best or dur < best[dn]:
                        best[dn] = dur

            sorted_res = sorted(best.items(), key=lambda x: x[1])
            if not sorted_res:
                return None

            p1_time = sorted_res[0][1]
            items = []
            for pos, (dnum, time_sec) in enumerate(sorted_res[:10], 1):
                dinfo = d_map.get(dnum, {})
                if pos == 1:
                    m, s = divmod(time_sec, 60)
                    t_str = f"{int(m)}:{s:06.3f}"
                else:
                    gap = time_sec - p1_time
                    t_str = f"+{gap:.3f}"

                items.append({
                    "position": pos,
                    "first_name": dinfo.get("first_name", ""),
                    "last_name": dinfo.get("last_name", ""),
                    "code": dinfo.get("name_acronym") or dinfo.get("last_name", "")[:3].upper(),
                    "nationality": dinfo.get("country_code", "F1"),
                    "team": dinfo.get("team_name", "Unknown"),
                    "time": t_str,
                    "number": str(dnum),
                })

            result = {
                "series": "FORMULA 1",
                "session_type": "PRACTICE",
                "category": "FREE PRACTICE RESULTS",
                "season": str(last_s.get("year", 2026)),
                "race_name": location,
                "circuit": last_s.get("circuit_short_name", ""),
                "title": f"FORMULA 1 {location.upper()} GRAND PRIX 2026",
                "subtitle": session_name,
                "items": items[:10],
                "all_items": items,
                "metric_header": "TIME",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_f1_practice_results: {e}", exc_info=True)
            return None

    # -------------------------------------------------------------
    # MOTOGP
    # -------------------------------------------------------------
    @staticmethod
    async def _get_motogp_current_season() -> str:
        cache_key = "motogp_curr_season"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        url = "https://api.motogp.pulselive.com/motogp/v1/results/seasons"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                seasons = await resp.json()
                current = [s for s in seasons if s.get("current")]
                if current:
                    season_id = current[0]["id"]
                else:
                    sorted_s = sorted(seasons, key=lambda x: x.get("year", 0), reverse=True)
                    season_id = sorted_s[0]["id"]
                _set_cache(cache_key, season_id, ttl=3600)
                return season_id

    @staticmethod
    async def _get_motogp_latest_event(season_id: str) -> Tuple[str, str]:
        """Mengambil nama dan kode negara dari event balapan MotoGP terakhir."""
        cache_key = f"motogp_latest_event_{season_id}"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        try:
            ev_url = f"https://api.motogp.pulselive.com/motogp/v1/results/events?seasonUuid={season_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get(ev_url, headers=headers) as resp:
                    events = await resp.json()

            finished = [e for e in events if e.get("status") == "FINISHED" and not e.get("test")]
            if not finished:
                finished = events
            if finished:
                le = finished[-1]
                name = le.get("sponsored_name") or le.get("name", "PT GRAND PRIX OF THAILAND")
                country_iso = le.get("country", {}).get("iso", "") if isinstance(le.get("country"), dict) else ""
                if not country_iso and isinstance(le.get("circuit"), dict):
                    country_iso = le.get("circuit", {}).get("nation", "")
                res = (name, country_iso or "THA")
                _set_cache(cache_key, res, ttl=3600)
                return res
        except Exception:
            pass
        return ("PT GRAND PRIX OF THAILAND", "THA")

    @staticmethod
    async def get_motogp_standings() -> Optional[Dict[str, Any]]:
        cache_key = "motogp_standings"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        try:
            season_id = await RacingService._get_motogp_current_season()
            cat_uuid = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"
            url = f"https://api.motogp.pulselive.com/motogp/v1/results/standings?seasonUuid={season_id}&categoryUuid={cat_uuid}"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            classification = data.get("classification", [])
            items = []
            for idx, rider in enumerate(classification):
                r_info = rider.get("rider", {}) or {}
                t_info = rider.get("team", {}) or {}
                c_info = rider.get("constructor", {}) or {}
                full_name = r_info.get("full_name", "")
                parts = full_name.split()
                if len(parts) > 1:
                    first = " ".join(parts[:-1])
                    last = parts[-1]
                else:
                    first = ""
                    last = full_name

                country = r_info.get("country", {}).get("iso", "") if isinstance(r_info.get("country"), dict) else ""
                team_name = t_info.get("name") or c_info.get("name") or "Unknown"

                raw_pos = rider.get("position")
                try:
                    pos = int(raw_pos) if raw_pos is not None else (idx + 1)
                except Exception:
                    pos = idx + 1

                raw_num = r_info.get("number")
                num_str = str(raw_num) if raw_num is not None else str(pos)

                items.append({
                    "position": pos,
                    "first_name": first,
                    "last_name": last,
                    "code": last[:3].upper() if last else "MGP",
                    "nationality": country,
                    "team": team_name,
                    "points": str(rider.get("points", 0)),
                    "wins": str(rider.get("race_wins", 0)),
                    "number": num_str,
                })

            if items:
                try:
                    p1_pts = float(items[0].get("points", 0))
                    items[0]["gap"] = ""
                    for it in items[1:]:
                        diff = int(p1_pts - float(it.get("points", 0)))
                        it["gap"] = f"-{diff}" if diff > 0 else "0"
                except Exception:
                    pass

            event_name, event_country = await RacingService._get_motogp_latest_event(season_id)

            result = {
                "series": "MOTOGP",
                "session_type": "STANDINGS",
                "category": "RIDER STANDINGS",
                "season": "2026",
                "title": "MOTOGP™ WORLD CHAMPIONSHIP 2026",
                "subtitle": "WORLD STANDINGS • OFFICIAL CLASSIFICATION",
                "title_l1": "RIDERS'",
                "title_l2": "CHAMPIONSHIP",
                "event": event_name,
                "event_country": event_country,
                "leader_status": "LEADER",
                "items": items[:10],
                "all_items": items,
                "metric_header": "POINTS",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_motogp_standings: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_motogp_session_results(session_type: str = "RAC") -> Optional[Dict[str, Any]]:
        """
        Mengambil hasil sesi MotoGP dari event terakhir:
        session_type:
            - 'RAC': Grand Prix Race
            - 'SPR': Sprint Race
            - 'Q': Qualifying
            - 'PR': Practice
            - 'FP': Free Practice
        """
        cache_key = f"motogp_session_{session_type.lower()}"
        cached = _get_cache(cache_key)
        if cached:
            return cached

        try:
            season_id = await RacingService._get_motogp_current_season()
            cat_uuid = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"
            headers = {"User-Agent": "Mozilla/5.0"}

            # Get events
            ev_url = f"https://api.motogp.pulselive.com/motogp/v1/results/events?seasonUuid={season_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(ev_url, headers=headers) as resp:
                    events = await resp.json()

            finished_events = [e for e in events if e.get("status") == "FINISHED" and not e.get("test")]
            if not finished_events:
                finished_events = events
            if not finished_events:
                return None
            last_event = finished_events[-1]
            event_id = last_event["id"]
            event_name = last_event.get("sponsored_name") or last_event.get("name", "Grand Prix")
            event_country = last_event.get("country", {}).get("iso", "") if isinstance(last_event.get("country"), dict) else ""
            if not event_country and isinstance(last_event.get("circuit"), dict):
                event_country = last_event.get("circuit", {}).get("nation", "")

            # Get sessions
            s_url = f"https://api.motogp.pulselive.com/motogp/v1/results/sessions?eventUuid={event_id}&categoryUuid={cat_uuid}"
            async with aiohttp.ClientSession() as session:
                async with session.get(s_url, headers=headers) as resp:
                    sessions = await resp.json()

            target_sessions = [s for s in sessions if s.get("type") == session_type]
            if not target_sessions:
                target_sessions = [s for s in sessions if s.get("type") == "RAC"]

            if not target_sessions:
                return None
            chosen_session = target_sessions[-1]

            c_url = f"https://api.motogp.pulselive.com/motogp/v1/results/session/{chosen_session['id']}/classification"
            async with aiohttp.ClientSession() as session:
                async with session.get(c_url, headers=headers) as resp:
                    clf = await resp.json()

            classification = clf.get("classification", [])
            items = []
            for idx, item in enumerate(classification):
                r_info = item.get("rider", {}) or {}
                t_info = item.get("team", {}) or {}
                c_info = item.get("constructor", {}) or {}
                full_name = r_info.get("full_name", "")
                parts = full_name.split()
                if len(parts) > 1:
                    first = " ".join(parts[:-1])
                    last = parts[-1]
                else:
                    first = ""
                    last = full_name

                country = r_info.get("country", {}).get("iso", "") if isinstance(r_info.get("country"), dict) else ""
                team_name = t_info.get("name") or c_info.get("name") or "Unknown"

                # Parse time or gap
                time_val = ""
                gap_val = ""
                if item.get("time"):
                    time_val = item["time"]
                elif item.get("best_lap") and item["best_lap"].get("time"):
                    time_val = item["best_lap"]["time"]
                else:
                    time_val = item.get("status", "")

                if idx > 0:
                    gap_first = item.get("gap", {}).get("first")
                    if gap_first and str(gap_first) != "0.000":
                        gap_val = f"+{gap_first}" if not str(gap_first).startswith("+") else str(gap_first)

                raw_pos = item.get("position")
                try:
                    pos = int(raw_pos) if raw_pos is not None else (idx + 1)
                except Exception:
                    pos = idx + 1

                raw_num = r_info.get("number")
                num_str = str(raw_num) if raw_num is not None else str(pos)

                items.append({
                    "position": pos,
                    "first_name": first,
                    "last_name": last,
                    "code": last[:3].upper() if last else "MGP",
                    "nationality": country,
                    "team": team_name,
                    "points": str(item.get("points", 0)),
                    "time": time_val,
                    "gap": gap_val,
                    "number": num_str,
                })

            session_label_map = {
                "RAC": "GRAND PRIX RACE",
                "SPR": "SPRINT RACE",
                "Q": "QUALIFYING",
                "PR": "PRACTICE",
                "FP": "FREE PRACTICE",
            }
            sub_title = session_label_map.get(session_type, "RACE RESULTS")

            if session_type == "RAC":
                t1, t2 = "GRAND PRIX", "RACE RESULTS"
                lead_stat = "WINNER"
            elif session_type == "SPR":
                t1, t2 = "SPRINT RACE", "RESULTS"
                lead_stat = "WINNER"
            elif session_type == "Q":
                t1, t2 = "QUALIFYING", "RESULTS"
                lead_stat = "POLE"
            else:
                t1, t2 = "FREE PRACTICE", "RESULTS"
                lead_stat = "FASTEST"

            result = {
                "series": "MOTOGP",
                "session_type": session_type,
                "category": sub_title,
                "season": "2026",
                "race_name": event_name,
                "title": f"MOTOGP™ {event_name.upper()} 2026",
                "subtitle": sub_title,
                "title_l1": t1,
                "title_l2": t2,
                "event": event_name,
                "event_country": event_country or "THA",
                "leader_status": lead_stat,
                "items": items[:10],
                "all_items": items,
                "metric_header": "TIME / GAP",
            }
            _set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"[RacingService] Error in get_motogp_session_results ({session_type}): {e}", exc_info=True)
            return None

    @staticmethod
    async def get_motogp_last_results() -> Optional[Dict[str, Any]]:
        return await RacingService.get_motogp_session_results("RAC")

