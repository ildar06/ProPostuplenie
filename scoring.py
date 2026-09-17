# -*- coding: utf-8 -*-
"""
Rule-based движок рекомендаций и roadmap.

Никакого внешнего LLM/API не требуется для базовой работы — это сознательное
решение, разрешённое условиями кейса ("rule-based логика"). Каждая
рекомендация сопровождается человекочитаемым объяснением "почему подходит",
собранным из конкретных совпадений с профилем (а не выдумано моделью).
"""

from data import PROGRAMS

BUDGET_LIMITS = {  # верхняя граница в тенге/год, None = без ограничений
    "grant": 0,
    "low": 1_500_000,
    "mid": 3_000_000,
    "any": None,
}


def _budget_fits(program, budget_key):
    limit = BUDGET_LIMITS.get(budget_key)
    if budget_key == "grant":
        # для "нужен грант" — годятся вузы с сильной грантовой историей
        return program["tuition_category"] in ("grant_only", "mid")
    if limit is None:
        return True
    return program["tuition_tenge_year"] <= limit


def score_program(program, profile):
    """Возвращает (score:int 0-100, reasons:list[str])."""
    score = 0
    reasons = []

    # интересы (до 35 баллов)
    matched_interests = [i for i in profile["interests"] if i in program["fields"]]
    if matched_interests:
        score += min(35, 15 * len(matched_interests))
        names = {
            "it": "IT", "business": "бизнес", "engineering": "инженерия",
            "medicine": "медицина", "law": "право", "humanities": "гуманитарные науки",
            "design": "дизайн", "science": "естественные науки",
        }
        reasons.append(
            "совпадает с вашими интересами: " + ", ".join(names[i] for i in matched_interests)
        )

    # балл ЕНТ (до 30 баллов)
    ent = profile.get("ent_score")
    if ent is not None:
        threshold = program["ent_threshold"]
        if ent >= threshold:
            margin = ent - threshold
            score += 30 if margin >= 15 else 22
            reasons.append(f"ваш балл ЕНТ ({ent}) выше проходного порога ({threshold}, демо)")
        elif ent >= threshold - 10:
            score += 10
            reasons.append(f"ваш балл ЕНТ ({ent}) близок к порогу ({threshold}, демо) — стоит подтянуть")
        else:
            score -= 10  # заметно ниже порога — не скрываем это

    # бюджет (до 20 баллов)
    if _budget_fits(program, profile["budget"]):
        score += 20
        if profile["budget"] == "grant":
            reasons.append("у вуза сильная грантовая история — шанс поступить на бюджет")
        else:
            reasons.append("стоимость обучения укладывается в ваш бюджет")
    else:
        score -= 15

    # город (до 10 баллов)
    if profile["city"] in ("Не важно / рассмотрю разные",):
        score += 5
    elif program["city"] == profile["city"]:
        score += 10
        reasons.append(f"находится в желаемом городе ({program['city']})")

    # язык / IELTS (до 5 баллов)
    langs = set(profile.get("languages", []))
    if langs & set(program["languages_required"]):
        score += 5

    return max(0, min(100, score)), reasons


def compute_recommendations(profile, top_n=3):
    scored = []
    for p in PROGRAMS:
        s, reasons = score_program(p, profile)
        scored.append({**p, "score": s, "reasons": reasons})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def compute_roadmap(profile, program):
    """Строит персональный план шагов под конкретную программу и профиль."""
    steps = []

    ent = profile.get("ent_score")
    if ent is not None and ent < program["ent_threshold"]:
        gap = program["ent_threshold"] - ent
        steps.append({
            "text": f"Подтянуть подготовку к ЕНТ: не хватает ~{gap} баллов до порога "
                    f"{program['ent_threshold']} (демо-порог) — записаться на курсы/репетитора",
            "done": False,
        })

    if program.get("min_ielts"):
        steps.append({
            "text": f"Сдать IELTS не ниже {program['min_ielts']} "
                    f"(или эквивалент) — записаться на экзамен заранее",
            "done": False,
        })

    steps.append({
        "text": "Собрать пакет документов: аттестат, удостоверение личности, "
                "фото, медсправка, мотивационное письмо",
        "done": False,
    })

    if profile["budget"] == "grant" or program["tuition_category"] in ("grant_only", "mid"):
        steps.append({
            "text": "Подготовить заявку на грант/стипендию вуза "
                    f"({program['scholarship_note']})",
            "done": False,
        })

    steps.append({
        "text": f"Подать документы до дедлайна: {program['deadline']}",
        "done": False,
    })

    steps.append({
        "text": "Проверить актуальные требования на официальном сайте вуза: "
                f"{program['source']}",
        "done": False,
    })

    return steps
