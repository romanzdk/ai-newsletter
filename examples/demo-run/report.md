# AI novinky za 10. 3. 2026

**1. Quillstack 2.0: běhy agentů lze obnovit od posledního kroku**  
Quillstack 2.0 je podle oficiálního blogu dostupný obecně a zapnuté obnovitelné běhy (resumable runs) pokračují od posledního uloženého kroku po pádu, timeoutu nebo rate limitu. Pro dlouhé agentní úlohy to znamená, že se po přerušení nemusí začínat od nuly.  
Výhrada: Kroky zapisující do externích systémů (e-mail, platby) se automaticky neopakují a bez označení idempotentní se zastaví na potvrzení; uložený stav běhu se drží 24 hodin na Free a 30 dní na Team.  
Zdroj: https://quillstack.dev/blog/quillstack-2-0

**2. Objev: Tidepool: terminálový dashboard pro sledování kódovacích agentů**  
Starší open-source projekt Tidepool, který v terminálu ukazuje běžící příkazy, spotřebu tokenů a změněné soubory kódovacích agentů, se objevil na Hacker News. Může pomoci sledovat, co agenti dělají, pokud váš agent zapisuje JSON logy.  
Výhrada: Repo existuje od června 2024, poslední release je z listopadu 2025, funguje jen na Linuxu a macOS a licence ani konkrétní podpora Claude Code, Codex či Cursor nejsou na stránce ověřeny.  
Zdroj: https://github.com/tidepool-dev/tidepool

**3. Lumen Agents přidává sdílené týmové workspaces**  
Lumen Agents zavedl týmové workspaces, kde více lidí sdílí agenty, secrets a historii běhů, s rolemi owner, editor a viewer. Tým může sdílet agenty a jejich historii běhů na jednom místě s rozdělením oprávnění.  
Výhrada: Funkce je dostupná jen v plánech Pro a Enterprise, nikoli ve Free, a postupně se zavádí během 7 dní, takže ji váš workspace nemusí mít hned.  
Zdroj: https://lumenagents.dev/changelog/team-workspaces

**4. AgentNotes 0.1: sdílený poznámkový blok pro kódovací agenty**  
Vyšla alfa verze AgentNotes 0.1, sdíleného scratchpadu, do kterého mohou kódovací agenti zapisovat a číst přes malé HTTP API. Tým, který běží více agentů, může sdílet průběžné poznámky mimo chat, pokud si službu sám provozuje.  
Výhrada: Je to early alpha pouze pro self-hosting; integrace s konkrétními nástroji ani stabilita nejsou na stránce doloženy.  
Zdroj: https://agentnotes.dev/

---
Kontrola: částečná. Zdroje: Hacker News, Cursor Changelog, Anthropic News, Claude Blog, GitHub anthropics/claude-code, GitHub openai/codex, GitHub pingdotgg/t3code, GitHub paperclipai/paperclip.
Nepodařilo se zkontrolovat: OpenAI News (https://openai.com/news/rss.xml: HTTP 503).
