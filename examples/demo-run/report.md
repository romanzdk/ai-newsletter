# AI novinky za 10. 3. 2026

**1. Quillstack 2.0: běhy agentů lze obnovit od posledního kroku**  
Quillstack 2.0 je dostupný a obnovitelné běhy agentů (resumable runs), které byly v betě od verze 1.8, jsou nyní stabilní a zapnuté ve výchozím nastavení. Běh přerušený pádem, timeoutem nebo rate limitem pokračuje od posledního uloženého kroku místo startu od začátku.  
Výhrada: Kroky zapisující do externích systémů (např. e-mail nebo platba) se automaticky nepřehrávají, takže je nutné je označit jako idempotentní; uložený stav se drží 24 hodin na Free a 30 dní na Team.  
Zdroj: https://github.com/quillstack/quillstack/releases/tag/v2.0.0

**2. Objev: Tidepool: terminál dashboard pro coding agenty**  
Projekt Tidepool se objevil na Hacker News (Show HN); repozitář ukazuje běžící příkazy, spotřebu tokenů a změněné soubory u coding agentů. Pro vývojáře, kteří používají více agentů, může být přehled o jejich aktivitě v terminálu užitečný; podporu konkrétních agentů ale z přečtených stránek nelze ověřit.  
Výhrada: Podle přečtené stránky funguje jen na Linuxu a macOS a licence ani seznam podporovaných agentů nebyly ověřeny.  
Zdroj: https://github.com/tidepool-dev/tidepool

**3. Lumen Agents přidává sdílené týmové workspaces**  
Týmové workspaces umožňují sdílet agenty, tajné údaje a historii běhů s rolemi owner, editor a viewer. Tým může mít agenty, tajné údaje a historii běhů na jednom místě s rozdělením rolí.  
Výhrada: Dostupné jen na plánech Pro a Enterprise a nasazování probíhá během 7 dní, takže se funkce nemusí ve workspace objevit hned.  
Zdroj: https://lumenagents.dev/changelog/team-workspaces

---
Kontrola: částečná. Zdroje: Hacker News, Cursor Changelog, Anthropic News, Claude Blog, GitHub anthropics/claude-code, GitHub openai/codex, GitHub pingdotgg/t3code, GitHub paperclipai/paperclip.
Nepodařilo se zkontrolovat: OpenAI News (https://openai.com/news/rss.xml: HTTP 503).
