# Copiado de Coach AI (coach/analyze.py) el 2026-10-29: extract_match_stats y sus
# auxiliares, sin cambios de lógica. No se copian los agregados (aggregate):
# en LDH los calcula ldh.publicar con n e intervalo.
"""Extraccion de metricas de partidas y agregados para coaching."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

QUEUE_NAMES = {
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    490: "Quickplay",
    700: "Clash",
    720: "ARAM Clash",
    1700: "Arena",
    1900: "URF",
}

ROLE_NAMES = {
    "TOP": "Top",
    "JUNGLE": "Jungla",
    "MIDDLE": "Mid",
    "BOTTOM": "ADC",
    "UTILITY": "Support",
}

# Minutos en los que medimos diferenciales de carril.
LANE_CHECKPOINTS = (10, 15)


def _duration_seconds(info: dict) -> int:
    """gameDuration viene en segundos en partidas modernas, ms en algunas viejas."""
    raw = info.get("gameDuration", 0) or 0
    if info.get("gameEndTimestamp") is None and raw > 10000:
        return raw // 1000
    return raw


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def find_participant(match: dict, puuid: str) -> dict | None:
    for p in match.get("info", {}).get("participants", []):
        if p.get("puuid") == puuid:
            return p
    return None


def find_lane_opponent(match: dict, me: dict) -> dict | None:
    """Enemigo en la misma posicion. Devuelve None si el matchup no es claro."""
    position = me.get("teamPosition") or me.get("individualPosition")
    if not position or position == "Invalid":
        return None
    candidates = [
        p
        for p in match["info"]["participants"]
        if p.get("teamId") != me.get("teamId")
        and (p.get("teamPosition") or p.get("individualPosition")) == position
    ]
    return candidates[0] if len(candidates) == 1 else None


def _frame_stats(frame: dict, participant_id: int) -> dict | None:
    pf = frame.get("participantFrames", {}).get(str(participant_id))
    if not pf:
        return None
    return {
        "cs": (pf.get("minionsKilled", 0) or 0) + (pf.get("jungleMinionsKilled", 0) or 0),
        "gold": pf.get("totalGold", 0) or 0,
        "xp": pf.get("totalXp", pf.get("xp", 0)) or 0,
    }


def lane_diffs(timeline: dict, my_id: int, opp_id: int | None) -> dict:
    """Diferenciales de CS/oro/XP contra el rival de carril en los checkpoints."""
    out: dict[str, Any] = {}
    frames = timeline.get("info", {}).get("frames", [])
    for minute in LANE_CHECKPOINTS:
        target_ms = minute * 60_000
        frame = None
        for f in frames:
            if f.get("timestamp", 0) <= target_ms + 30_000:
                frame = f
            else:
                break
        if frame is None or frame.get("timestamp", 0) < target_ms - 60_000:
            continue  # la partida termino antes de este checkpoint
        mine = _frame_stats(frame, my_id)
        if not mine:
            continue
        out[f"cs_at_{minute}"] = mine["cs"]
        out[f"gold_at_{minute}"] = mine["gold"]
        if opp_id:
            theirs = _frame_stats(frame, opp_id)
            if theirs:
                out[f"cs_diff_at_{minute}"] = mine["cs"] - theirs["cs"]
                out[f"gold_diff_at_{minute}"] = mine["gold"] - theirs["gold"]
                out[f"xp_diff_at_{minute}"] = mine["xp"] - theirs["xp"]
    return out


def _phase_key(minute: float) -> str:
    if minute < 10:
        return "early_0_10"
    if minute < 20:
        return "mid_10_20"
    return "late_20_plus"


def timeline_events(timeline: dict, match: dict, my_id: int) -> dict:
    """Todo lo que sacamos del timeline en una sola pasada.

    - deaths_by_phase / takedowns_by_phase: cuando mueres y cuando impactas.
    - death_events: cada muerte con minuto, posicion, verdugo y si fue "solo"
      (sin asistencias enemigas = te cazaron aislado).
    - build_order: items completados (2000+ oro) con su minuto de compra.
    - control_ward_minutes: minuto de cada ward de control colocada.
    """
    from .static_data import get_static

    static = get_static()
    champ_by_id = {
        p.get("participantId"): p.get("championName")
        for p in match.get("info", {}).get("participants", [])
    }

    my_team = next(
        (p.get("teamId") for p in match.get("info", {}).get("participants", [])
         if p.get("participantId") == my_id),
        None,
    )

    deaths = {"early_0_10": 0, "mid_10_20": 0, "late_20_plus": 0}
    takedowns = {"early_0_10": 0, "mid_10_20": 0, "late_20_plus": 0}
    death_events: list[dict] = []
    purchases: list[dict] = []
    control_ward_minutes: list[float] = []
    # Con que aliado convierto mis asistencias (sinergia).
    assist_partners: dict[str, int] = {}

    for frame in timeline.get("info", {}).get("frames", []):
        for event in frame.get("events", []):
            etype = event.get("type")
            minute = round(event.get("timestamp", 0) / 60_000, 1)

            if etype == "CHAMPION_KILL":
                assists = event.get("assistingParticipantIds") or []
                if event.get("victimId") == my_id:
                    deaths[_phase_key(minute)] += 1
                    pos = event.get("position") or {}
                    death_events.append(
                        {
                            "min": minute,
                            "x": pos.get("x"),
                            "y": pos.get("y"),
                            "killer": champ_by_id.get(event.get("killerId")),
                            "solo": not assists,
                        }
                    )
                elif event.get("killerId") == my_id or my_id in assists:
                    takedowns[_phase_key(minute)] += 1
                    matador = event.get("killerId")
                    if matador != my_id:
                        nombre = champ_by_id.get(matador)
                        if nombre:
                            assist_partners[nombre] = assist_partners.get(nombre, 0) + 1

            elif etype == "ITEM_PURCHASED" and event.get("participantId") == my_id:
                purchases.append({"min": minute, "id": event.get("itemId")})

            elif etype == "ITEM_UNDO" and event.get("participantId") == my_id:
                before = event.get("beforeId")
                for i in range(len(purchases) - 1, -1, -1):
                    if purchases[i]["id"] == before:
                        purchases.pop(i)
                        break

            elif (
                etype == "WARD_PLACED"
                and event.get("creatorId") == my_id
                and event.get("wardType") == "CONTROL_WARD"
            ):
                control_ward_minutes.append(minute)

    build_order = [
        {"min": p["min"], "item": static.item_name(p["id"])}
        for p in purchases
        if p["id"] and static.is_completed_item(p["id"])
    ]

    return {
        "deaths_by_phase": deaths,
        "takedowns_by_phase": takedowns,
        "death_events": death_events,
        "solo_deaths": sum(1 for d in death_events if d["solo"]),
        "build_order": build_order,
        "first_item_min": build_order[0]["min"] if build_order else None,
        "control_ward_minutes": control_ward_minutes,
        "assist_partners": dict(
            sorted(assist_partners.items(), key=lambda kv: -kv[1])
        ),
    }


def extract_match_stats(match: dict, puuid: str, timeline: dict | None = None) -> dict | None:
    """Reduce una partida completa a las metricas del jugador."""
    info = match.get("info", {})
    me = find_participant(match, puuid)
    if me is None:
        return None

    duration = _duration_seconds(info)
    # LDH: remake = gameEndedInEarlySurrender, no "menos de 5 minutos". Una derrota real
    # de 286 s (LA2_1621150801) cuenta en el W/L de Riot y con el corte por duración se perdía.
    if any(p.get("gameEndedInEarlySurrender") for p in info.get("participants", [])):
        return None
    minutes = duration / 60
    ch = me.get("challenges", {}) or {}

    cs = (me.get("totalMinionsKilled", 0) or 0) + (me.get("neutralMinionsKilled", 0) or 0)
    team_kills = sum(
        p.get("kills", 0)
        for p in info.get("participants", [])
        if p.get("teamId") == me.get("teamId")
    )

    stats: dict[str, Any] = {
        "match_id": match.get("metadata", {}).get("matchId"),
        "queue_id": info.get("queueId"),
        "queue": QUEUE_NAMES.get(info.get("queueId"), f"Queue {info.get('queueId')}"),
        "game_creation": info.get("gameCreation"),
        "patch": ".".join((info.get("gameVersion") or "").split(".")[:2]),
        "duration_min": round(minutes, 1),
        "champion": me.get("championName"),
        "role": ROLE_NAMES.get(me.get("teamPosition") or "", me.get("teamPosition") or "?"),
        "win": bool(me.get("win")),
        "kills": me.get("kills", 0),
        "deaths": me.get("deaths", 0),
        "assists": me.get("assists", 0),
        "kda": round(_safe_div(me.get("kills", 0) + me.get("assists", 0), max(me.get("deaths", 0), 1)), 2),
        "cs": cs,
        "cs_per_min": round(_safe_div(cs, minutes), 2),
        "gold": me.get("goldEarned", 0),
        "gold_per_min": round(_safe_div(me.get("goldEarned", 0), minutes), 1),
        "damage_to_champions": me.get("totalDamageDealtToChampions", 0),
        "damage_per_min": round(_safe_div(me.get("totalDamageDealtToChampions", 0), minutes), 1),
        "damage_share": round(ch.get("teamDamagePercentage", 0) * 100, 1) if ch.get("teamDamagePercentage") else None,
        "kill_participation": (
            round(ch["killParticipation"] * 100, 1)
            if ch.get("killParticipation") is not None
            else round(_safe_div(me.get("kills", 0) + me.get("assists", 0), max(team_kills, 1)) * 100, 1)
        ),
        "vision_score": me.get("visionScore", 0),
        "vision_per_min": round(_safe_div(me.get("visionScore", 0), minutes), 2),
        "wards_placed": me.get("wardsPlaced", 0),
        "wards_killed": me.get("wardsKilled", 0),
        "control_wards": me.get("detectorWardsPlaced", 0),
        "time_dead_sec": me.get("totalTimeSpentDead", 0),
        "time_dead_pct": round(_safe_div(me.get("totalTimeSpentDead", 0), duration) * 100, 1),
        "champ_level": me.get("champLevel", 0),
        "solo_kills": ch.get("soloKills", 0),
        "turret_plates": ch.get("turretPlatesTaken", 0),
        "objectives_stolen": me.get("objectivesStolen", 0),
        "first_blood": bool(me.get("firstBloodKill")),
        "skillshots_dodged": ch.get("skillshotsDodged"),
        # --- defensa y aporte no ofensivo
        "damage_taken_per_min": round(_safe_div(me.get("totalDamageTaken", 0), minutes), 1),
        "damage_taken_share": round(ch.get("damageTakenOnTeamPercentage", 0) * 100, 1)
        if ch.get("damageTakenOnTeamPercentage") is not None
        else None,
        "self_mitigated_per_min": round(_safe_div(me.get("damageSelfMitigated", 0), minutes), 1),
        "ally_heal_shield": (me.get("totalHealsOnTeammates", 0) or 0)
        + (me.get("totalDamageShieldedOnTeammates", 0) or 0),
        "cc_time_sec": me.get("timeCCingOthers", 0),
        "saves": ch.get("saveAllyFromDeath", 0),
        "picks_with_ally": ch.get("immobilizeAndKillWithAlly", 0),
        "lane_minions_first_10": ch.get("laneMinionsFirst10Minutes"),
        "vision_advantage_vs_opp": round(ch["visionScoreAdvantageLaneOpponent"], 2)
        if ch.get("visionScoreAdvantageLaneOpponent") is not None
        else None,
        # --- precision de habilidades
        "skillshots_hit": ch.get("skillshotsHit"),
        "skillshots_early": ch.get("landSkillShotsEarlyGame"),
        "ability_uses": ch.get("abilityUses"),
        "casts_q": me.get("spell1Casts"),
        "casts_w": me.get("spell2Casts"),
        "casts_e": me.get("spell3Casts"),
        "casts_r": me.get("spell4Casts"),
        # --- supervivencia bajo presion
        "survived_low_hp": ch.get("survivedSingleDigitHpCount"),
        "survived_3_cc": ch.get("survivedThreeImmobilizesInFight"),
        "tanked_and_survived": ch.get("tookLargeDamageSurvived"),
        "deaths_by_champs": ch.get("deathsByEnemyChamps"),
        "longest_time_living": me.get("longestTimeSpentLiving"),
        # --- MIS objetivos (no los del equipo)
        "my_dragons": ch.get("dragonTakedowns"),
        "my_heralds": ch.get("riftHeraldTakedowns"),
        "my_barons": ch.get("baronTakedowns"),
        "my_turrets": ch.get("turretTakedowns"),
        "earliest_dragon_sec": ch.get("earliestDragonTakedown"),
        "first_turret_killed": ch.get("firstTurretKilled"),
        "objectives_stolen_epic": ch.get("epicMonsterSteals"),
        # --- dominio de linea
        "won_lane_gold_exp": ch.get("laningPhaseGoldExpAdvantage"),
        "won_early_lane": ch.get("earlyLaningPhaseGoldExpAdvantage"),
        "max_cs_advantage": ch.get("maxCsAdvantageOnLaneOpponent"),
        "max_level_lead": ch.get("maxLevelLeadLaneOpponent"),
        "max_kill_deficit": ch.get("maxKillDeficit"),
        # --- jungla
        "jungle_cs_before_10": ch.get("jungleCsBefore10Minutes"),
        "enemy_jungle_taken": ch.get("enemyJungleMonsterKills"),
        "own_jungle_taken": ch.get("alliedJungleMonsterKills"),
        "scuttles": ch.get("scuttleCrabKills"),
        "buffs_stolen": ch.get("buffsStolen"),
        # --- picks y peleas
        "pick_kills_with_ally": ch.get("pickKillWithAlly"),
        "kills_after_hidden": ch.get("killAfterHiddenWithAlly"),
        "outnumbered_kills": ch.get("outnumberedKills"),
        "quick_solo_kills": ch.get("quickSoloKills"),
        "takedowns_first_x": ch.get("takedownsFirstXMinutes"),
        "bounty_gold": ch.get("bountyGold"),
        # --- vision detallada
        "stealth_wards": ch.get("stealthWardsPlaced"),
        "ward_takedowns": ch.get("wardTakedowns"),
        "ward_takedowns_pre20": ch.get("wardTakedownsBefore20M"),
        "wards_guarded": ch.get("wardsGuarded"),
        "support_quest_in_time": ch.get("completeSupportQuestInTime"),
        # --- contexto de la partida
        "had_open_nexus": ch.get("hadOpenNexus"),
        "lost_inhibitor": ch.get("lostAnInhibitor"),
        "had_afk_teammate": bool(ch.get("hadAfkTeammate")) if ch.get("hadAfkTeammate") is not None else None,
        "early_surrender": bool(me.get("gameEndedInEarlySurrender")),
        "surrendered": bool(me.get("gameEndedInSurrender")),
        # --- comunicacion
        "pings_total": sum(
            me.get(k, 0) or 0
            for k in (
                "allInPings", "assistMePings", "basicPings", "commandPings",
                "dangerPings", "enemyMissingPings", "enemyVisionPings",
                "getBackPings", "holdPings", "needVisionPings", "onMyWayPings",
                "pushPings", "visionClearedPings",
            )
        ),
        "mia_pings": me.get("enemyMissingPings", 0),
    }

    # Precision: aciertos sobre los lanzamientos que son skillshot (Q/E/R).
    # El denominador es aproximado (la R dispara varias veces por activacion),
    # pero se calcula igual en todas las partidas, asi que la tendencia es valida.
    tiros = sum(me.get(k, 0) or 0 for k in ("spell1Casts", "spell3Casts", "spell4Casts"))
    if ch.get("skillshotsHit") is not None and tiros >= 10:
        stats["skillshot_accuracy"] = round(100 * ch["skillshotsHit"] / tiros, 1)
        stats["skillshot_attempts"] = tiros

    _add_loadout(stats, me)
    _add_teams(stats, match, me)

    opponent = find_lane_opponent(match, me)
    if opponent:
        stats["opponent_champion"] = opponent.get("championName")

    if timeline:
        my_id = me.get("participantId")
        opp_id = opponent.get("participantId") if opponent else None
        stats.update(lane_diffs(timeline, my_id, opp_id))
        stats.update(timeline_events(timeline, match, my_id))

    return stats


def _add_loadout(stats: dict, me: dict) -> None:
    """Items finales, runas y hechizos de invocador, con nombres legibles."""
    from .static_data import get_static

    static = get_static()
    item_ids = [me.get(f"item{i}", 0) or 0 for i in range(6)]
    stats["items"] = [static.item_name(i) for i in item_ids if i]
    stats["trinket"] = static.item_name(me["item6"]) if me.get("item6") else None
    stats["summoner_spells"] = [
        static.spell_name(me[k]) for k in ("summoner1Id", "summoner2Id") if me.get(k)
    ]

    styles = (me.get("perks") or {}).get("styles") or []
    for style in styles:
        if style.get("description") == "primaryStyle":
            selections = style.get("selections") or []
            if selections:
                stats["keystone"] = static.rune_name(selections[0].get("perk", 0))
            stats["rune_primary"] = static.style_name(style.get("style", 0))
        elif style.get("description") == "subStyle":
            stats["rune_secondary"] = static.style_name(style.get("style", 0))


def _add_teams(stats: dict, match: dict, me: dict) -> None:
    """Composiciones y objetivos por equipo."""
    info = match.get("info", {})
    my_team = me.get("teamId")
    stats["allies"] = [
        p.get("championName")
        for p in info.get("participants", [])
        if p.get("teamId") == my_team and p.get("puuid") != me.get("puuid")
    ]
    stats["enemies"] = [
        p.get("championName")
        for p in info.get("participants", [])
        if p.get("teamId") != my_team
    ]
    stats["enemy_had_afk"] = any(
        bool((p.get("challenges") or {}).get("hadAfkTeammate"))
        for p in info.get("participants", [])
        if p.get("teamId") != my_team
    )
    for team in info.get("teams", []):
        prefix = "team" if team.get("teamId") == my_team else "enemy"
        obj = team.get("objectives") or {}
        stats[f"{prefix}_objectives"] = {
            name: (obj.get(name) or {}).get("kills", 0)
            for name in ("baron", "dragon", "riftHerald", "horde", "tower", "inhibitor")
        }
        if prefix == "team":
            stats["first_tower_team"] = bool((obj.get("tower") or {}).get("first"))
        if team.get("teamId") == my_team:
            stats["bans_team"] = [b.get("championId") for b in team.get("bans") or [] if b.get("championId", -1) > 0]

