"""Step 9 output: the Czech digest as Markdown. Plain formatting, no model call."""

from datetime import date

from ai_newsletter.models import RunRecord

STATUS = {"complete": "úplná", "partial": "částečná", "failed": "nedokončená"}


def render(record: RunRecord) -> str:
    title = f"# AI novinky za {_czech_date(record.day)}"
    if record.status == "failed":
        reasons = "; ".join(record.errors) or "neznámá chyba"
        return f"{title}\n\nKontrola nebyla dokončena, přehled za tento den není k dispozici.\nDůvod: {reasons}\n"

    items = [event.verdict for event in record.events if event.selected and event.verdict]
    parts = [title, ""]
    if not items:
        parts += ["V prověřených zdrojích nebylo nic podstatného.", ""]
    for number, item in enumerate(items, 1):
        label = "Objev: " if item.kind == "discovery" else ""
        parts.append(f"**{number}. {label}{item.title}**  ")
        parts.append(f"{item.what_changed} {item.why_it_matters}  ")
        if item.caveat:
            parts.append(f"Výhrada: {item.caveat}  ")
        parts += [f"Zdroj: {item.source_url}", ""]

    parts.append("---")
    parts.append(f"Kontrola: {STATUS[record.status]}. Zdroje: {', '.join(c.source for c in record.coverage if c.ok)}.")
    gaps = [f"{c.source} ({c.error})" for c in record.coverage if not c.ok]
    if gaps:
        parts.append(f"Nepodařilo se zkontrolovat: {'; '.join(gaps)}.")
    unverified = [event.plan.label for event in record.events if event.error]
    if unverified:
        parts.append(f"Neověřeno ({len(unverified)}): {'; '.join(unverified)}.")
    return "\n".join(parts) + "\n"


def _czech_date(day: date) -> str:
    return f"{day.day}. {day.month}. {day.year}"
