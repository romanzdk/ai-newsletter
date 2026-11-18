# AI novinky za 10. 3. 2026

**1. Quillstack 2.0: resumable runs jsou stabilní a výchozí**  
Quillstack 2.0 je vydán jako generally available a obnovení běhů agenta od posledního uloženého kroku je ve verzi 2.0 stabilní a zapnuté ve výchozím nastavení. Běh agenta přerušený pádem, timeoutem nebo rate limitem může pokračovat od posledního uloženého kroku místo restartu od začátku.  
Výhrada: Kroky zapisující do externích systémů se nereplayují automaticky a uložený stav běhu se drží jen 24 hodin na Free plánu a 30 dní na Team plánu.  
Zdroj: https://quillstack.dev/blog/quillstack-2-0

**2. Objev: Tidepool: terminálový dashboard pro coding agenty**  
Na Hacker News se objevil open-source projekt Tidepool, který v terminálu zobrazuje aktivitu coding agentů. Hodí se pro sledování příkazů, tokenů a změn souborů u agentů, které zapisují JSON logy.  
Výhrada: Poslední release je z listopadu 2025, podporu konkrétních agentů a licenci jsem neověřil a nástroj běží jen na Linuxu a macOS.  
Zdroj: https://github.com/tidepool-dev/tidepool

**3. Lumen Agents přidává sdílené týmové workspace**  
Týmové workspace umožňují více lidem sdílet agenty, tajné údaje a historii běhů na jednom místě, s rolemi owner, editor a viewer. Tým může spravovat agenty a jejich běhy společně místo jednotlivých účtů.  
Výhrada: Funkce je dostupná jen v plánech Pro a Enterprise, zavádí se postupně během 7 dnů a stránka neuvádí ceny.  
Zdroj: https://lumenagents.dev/changelog/team-workspaces

---
Kontrola: částečná. Zdroje: Hacker News, Cursor Changelog, Anthropic News, Claude Blog, GitHub anthropics/claude-code, GitHub openai/codex, GitHub pingdotgg/t3code, GitHub paperclipai/paperclip.
Mezery v pokrytí: OpenAI News (https://openai.com/news/rss.xml: HTTP 503).
