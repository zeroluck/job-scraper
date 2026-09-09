# LinkedIn Targeted Relevance Audit - 2026-09-09

## Decision record

- Scope: LinkedIn Canada memberships in `technology_delivery` and `ai_workflow_automation`.
- Baseline: configuration revision 9, created `2026-09-07T12:33:02.48083+00:00`; the exact snapshot is at `linkedin-targeted-relevance-samples-2026-09-09.json#/frozen_revision/configuration`.
- Rollback: pre-audit revision 5, recovered from the prior audit. Supplied evidence identifies revision 5 but does not include its configuration body.
- Proposed: revision 10 changes only filter arrays for the two audited lanes. Search queries and all other lane fields remain unchanged.
- Applied: production revision 10 was applied at `2026-09-09 08:34:10 UTC` by remote migration `20260909083410 apply_refined_target_profiles`; all 13 active queries remained active.
- Corrected: remote migration `20260909084057 correct_refined_target_profiles_exact_content` corrected MCP transcription only and preserved revision 10 with the exact proposed profile text. Final live and local profile hashes match. No query or non-target lane changed.
- Backfilled: all 3,502 predeclared membership changes were applied across the 8,348 target memberships; a second dry run scanned all 8,348 and found zero changes.
- Safety: all known relevant sentinels are directly included and all known borderline sentinels are non-filtered. The filtered guard found false exclusions, so current filter status is not truth.
- Query decision: no query removal is recommended. Sole-query yields are descriptive marginal evidence, not causal query estimates.

## Method

Job titles and descriptions were treated as untrusted evidence and never as instructions. Coding was model-assisted independent single coding, not human double coding. There was no second human coder, inter-rater statistic, or human adjudication.

The frozen population contains 8,348 lane memberships: 6,728 `technology_delivery` and 1,620 `ai_workflow_automation`. The constructor retained LinkedIn rows, loaded revision 9 and its enabled queries, and treated a query as post-change provenance only when `matched_queries[].observed_at >= 2026-09-07T12:33:02.48083+00:00`. `observed_active_queries` records active-query evidence at or after that cutoff. `new_included` requires stored `included` and `first_matched_at >= cutoff`; `post_revision_review` requires stored `review` plus post-cutoff active-query provenance; `filtered_guard` uses stored `filtered`; each sole-query population requires exact `observed_active_queries == [query]`.

Each stratum is deterministic SRS-WOR: sort by ascending `md5(f'{job_id}:{seed}')`, tie-break by `job_id`, and take the requested size. The 11 strata contain 325 draws but 307 unique lane/job IDs because strata overlap. All populations, sample IDs, orderings, labels, rationales, counts, and intervals replay exactly.

Labels are `relevant`, `borderline`, `clearly_irrelevant`, and `insufficient`. Wilson 95% intervals use `z = 1.959963984540054` for `(relevant + borderline) / decided`, excluding `insufficient` from the denominator. They do not include finite-population correction or coding uncertainty.

## Frozen strata

| Lane | Stratum/query | Seed | Population | n | Relevant | Borderline | Clear irrelevant | Insufficient | Relevant + borderline | Wilson 95% |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `technology_delivery` | new_included | `targeted-2026-09-08:new-included` | 425 | 50 | 15 | 12 | 22 | 1 | 55.1% | 41.3%-68.1% |
| `technology_delivery` | post_revision_review | `targeted-2026-09-08:post-revision-review` | 100 | 25 | 9 | 5 | 9 | 2 | 60.9% | 40.8%-77.8% |
| `technology_delivery` | filtered_guard | `targeted-2026-09-08:filtered-guard` | 381 | 25 | 3 | 1 | 21 | 0 | 16.0% | 6.4%-34.7% |
| `technology_delivery` | sole_active_query / IT technology project manager | `targeted-2026-09-08:sole-query:IT technology project manager` | 119 | 25 | 9 | 7 | 8 | 1 | 66.7% | 46.7%-82.0% |
| `technology_delivery` | sole_active_query / gestionnaire de projet informatique TI | `targeted-2026-09-08:sole-query:gestionnaire de projet informatique TI` | 195 | 25 | 8 | 7 | 10 | 0 | 60.0% | 40.7%-76.6% |
| `technology_delivery` | sole_active_query / technical program delivery manager | `targeted-2026-09-08:sole-query:technical program delivery manager` | 125 | 25 | 8 | 2 | 15 | 0 | 40.0% | 23.4%-59.3% |
| `ai_workflow_automation` | new_included | `targeted-2026-09-08:new-included` | 121 | 50 | 30 | 14 | 6 | 0 | 88.0% | 76.2%-94.4% |
| `ai_workflow_automation` | post_revision_review | `targeted-2026-09-08:post-revision-review` | 322 | 25 | 5 | 3 | 17 | 0 | 32.0% | 17.2%-51.6% |
| `ai_workflow_automation` | filtered_guard | `targeted-2026-09-08:filtered-guard` | 97 | 25 | 1 | 6 | 18 | 0 | 28.0% | 14.3%-47.6% |
| `ai_workflow_automation` | sole_active_query / AI solutions engineer LLM workflow integration | `targeted-2026-09-08:sole-query:AI solutions engineer LLM workflow integration` | 148 | 25 | 2 | 3 | 20 | 0 | 20.0% | 8.9%-39.1% |
| `ai_workflow_automation` | sole_active_query / agentic AI engineer RAG workflow automation | `targeted-2026-09-08:sole-query:agentic AI engineer RAG workflow automation` | 128 | 25 | 4 | 4 | 17 | 0 | 32.0% | 17.2%-51.6% |

Every sample ID is at `linkedin-targeted-relevance-samples-2026-09-09.json#/sampling/strata`. Every frozen targeted label and rationale is at `linkedin-targeted-relevance-samples-2026-09-09.json#/labels`; retained job text and provenance are at `linkedin-targeted-relevance-samples-2026-09-09.json#/jobs`.

## Query attribution

Associations are non-exclusive because one sampled job can carry both active queries. Counts cover unique sampled jobs associated with each query, regardless of stratum.

| Lane | Query | Unique jobs | Relevant | Borderline | Clear irrelevant | Insufficient |
|---|---|---:|---:|---:|---:|---:|
| `technology_delivery` | IT technology project manager | 61 | 21 | 16 | 21 | 3 |
| `technology_delivery` | gestionnaire de projet informatique TI | 77 | 25 | 22 | 28 | 2 |
| `technology_delivery` | technical program delivery manager | 48 | 16 | 7 | 23 | 2 |
| `ai_workflow_automation` | AI solutions engineer LLM workflow integration | 86 | 33 | 18 | 35 | 0 |
| `ai_workflow_automation` | agentic AI engineer RAG workflow automation | 87 | 38 | 18 | 31 | 0 |

Sole-query marginal relevant-or-borderline yields are:

- `IT technology project manager`: 16/24 decided, 66.7%, Wilson 46.7%-82.0%.
- `gestionnaire de projet informatique TI`: 15/25, 60.0%, Wilson 40.7%-76.6%.
- `technical program delivery manager`: 10/25, 40.0%, Wilson 23.4%-59.3%.
- `AI solutions engineer LLM workflow integration`: 5/25, 20.0%, Wilson 8.9%-39.1%.
- `agentic AI engineer RAG workflow automation`: 8/25, 32.0%, Wilson 17.2%-51.6%.

No query removals are recommended from these overlapping, unweighted marginal samples.

## Error clusters

The complete clear-false-positive role-family count maps are at `linkedin-targeted-filter-impact-2026-09-09.json#/frozen_targeted_results/false_positive_role_family_clusters_complete`. Leading technology families are product management (5), construction project management (4), and civil construction project management (3). Leading AI families are data engineering (9), backend engineering (7), software engineering (5), and site reliability engineering (4). Generic project/construction/product retrieval drives technology noise; conventional data/software/platform/research jobs carrying incidental AI, workflow, integration, or automation language drive AI noise.

The stored-filter guard found false exclusions:

- `technology_delivery`: 3 relevant and 1 borderline among 25 stored-filtered rows: `4464430132`, `4326504469`, `4406707733`, `4454251915`.
- `ai_workflow_automation`: 1 relevant and 6 borderline among 25 stored-filtered rows: `4435482704`, `4445258802`, `4394723076`, `4463768039`, `4464645823`, `4462310081`, `4463632165`.

This directly demonstrates that stored `filter_status` and `filter_reason` are operational metadata, not relevance truth.

## Exclusion safety

All candidate title patterns were replayed against the complete supplied lane populations. Stored title counts, current recomputed title counts, every matching current job ID, and every title count are at `linkedin-targeted-filter-impact-2026-09-09.json#/exclusion_audit`.

| Lane | Candidate pattern | Stored matches | Current replay | Recall n | Relevant | Borderline | Clear irrelevant | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `technology_delivery` | 1 | 118 | 119 | 25 | 1 | 2 | 22 | Reject English branches; retain narrowed French family |
| `technology_delivery` | 2 | 10 | 10 | 10 | 5 | 1 | 4 | Reject Scrum branches; retain Sales Program Manager |
| `technology_delivery` | 3 | 166 | 166 | 25 | 0 | 0 | 25 | Keep unchanged |
| `technology_delivery` | 4 | 3 | 3 | 3 | 0 | 0 | 3 | Keep unchanged |
| `ai_workflow_automation` | 1 | 2 | 2 | 2 | 0 | 0 | 2 | Keep unchanged |
| `ai_workflow_automation` | 2 | 10 | 10 | 10 | 0 | 0 | 10 | Keep unchanged |

One source-snapshot difference is preserved rather than hidden: stored technology candidate pattern 1 has 118 matches, while replay on the supplied later 8,348-row population has 119. The added title is `Technical Product Manager – GenAI Programmes` (one row). Other candidate match sets replay exactly.

Rejected unsafe patterns:

- Technology candidate pattern 1's deterministic 25-row sample includes relevant `4450182537` and borderline `4463239132` and `4433237837`. All English product-manager/product-owner branches were rejected. Generic English titles cannot separate delivery-heavy `4444300627` and `4437406658` from ordinary product ownership. The final pattern retains only a two-row French product-owner family.
- Technology candidate pattern 2's complete 10-row review includes five relevant and one borderline Scrum roles. All Scrum branches were rejected, including the unsupported one-off `Delivery Practice Owner, Scrum Master`; only the one clearly irrelevant Sales Program Manager family remains.
- Broad AI exclusions such as `software engineer`, `data scientist`, `solutions architect`, `infrastructure`, `research`, or `model training` were rejected. Exclusions run before includes and these terms cause known relevant or borderline workflow implementation roles to be filtered.

The final technology title exclusions match 2, 1, 166, and 3 current rows. The three narrowed pattern-1/pattern-2 matches are manually confirmed clearly irrelevant; unchanged patterns 3 and 4 have deterministic recall samples totaling 28/28 clearly irrelevant. Final AI exclusions match 2 and 10 rows; their complete 12/12 set is clearly irrelevant. Every recall sample row, full supplied description, verdict, and rationale is at `linkedin-targeted-filter-impact-2026-09-09.json#/exclusion_audit`.

## Exact proposed and applied profile changes

Revision 9 to proposed revision 10 changes only `title_exclude`, `title_include`, and `description_include` for the two audited lanes. `description_exclude` remains empty; evaluator company and entry-level blocklists remain empty. Queries and every other lane field compare equal as parsed JSON. Exact before, after, added, and removed arrays are at `linkedin-targeted-filter-impact-2026-09-09.json#/exact_profile_changes`.

Production revision 10 was applied at `2026-09-09 08:34:10 UTC` by `20260909083410 apply_refined_target_profiles`. The follow-up remote migration `20260909084057 correct_refined_target_profiles_exact_content` fixed MCP transcription only, retained configuration revision 10, and made the live profile text exactly equal to the local proposed profiles shown here. Final live and local profile hashes match. The migrations did not alter any query or non-target lane, and the active-query count remained 13.

### `technology_delivery` final evaluator profile

```json
{
  "company_blocklist": [],
  "desc_blocklist": [],
  "description_include": [
    "(?sx)\\A(?=.*(?:\\b(?:lead(?:s|ing)?|manage(?:s|d|ing)?|own(?:s|ed|ing)?|oversee(?:s|ing)?|direct(?:s|ing)?|accountable\\s+for|responsible\\s+for)\\b.{0,180}\\b(?:delivery|implementation|deployment|migration|transformation|portfolio|workstreams?|go-live)\\b|\\b(?:lead(?:s|ing)?|manage(?:s|d|ing)?|own(?:s|ed|ing)?|oversee(?:s|ing)?|direct(?:s|ing)?|accountable\\s+for|responsible\\s+for)\\b.{0,180}\\b(?:projects?|programs?)\\b(?=.{0,700}\\b(?:scope|schedule|budget|risks?|vendors?|stakeholders?|resources?|timeline|financials?)\\b)|\\b(?:end-to-end|full\\s+lifecycle)\\b.{0,100}\\b(?:delivery|implementation|deployment|migration|transformation|portfolio|workstreams?|go-live|projects?|programs?)\\b|\\b(?:dirig(?:e|er|ez)|g[eé]r(?:e|er|ez)|pilot(?:e|er|ez)|supervis(?:e|er|ez)|responsable\\s+de)\\b.{0,180}\\b(?:livraison|mise\\s+en\\s+[oœ]uvre|implantation|d[eé]ploiement|migration|transformation|portefeuille)\\b|\\b(?:dirig(?:e|er|ez)|g[eé]r(?:e|er|ez)|pilot(?:e|er|ez)|supervis(?:e|er|ez)|responsable\\s+de)\\b.{0,180}\\b(?:projets?|programmes?)\\b(?=.{0,700}\\b(?:port[eé]e|[eé]ch[eé]ancier|budget|risques?|fournisseurs?|parties\\s+prenantes|ressources?)\\b)|\\b(?:de\\s+bout\\s+en\\s+bout|cycle\\s+de\\s+vie\\s+complet)\\b.{0,100}\\b(?:livraison|mise\\s+en\\s+[oœ]uvre|implantation|d[eé]ploiement|migration|transformation|portefeuille|projets?|programmes?)\\b))(?=.*(?:\\b(?:SaaS|ERP|CRM|SAP|Salesforce|ServiceNow|Workday|Dynamics\\s*365|Shopify(?:\\s+Plus)?|NetSuite|DevOps|CI/CD|cybersecurity|IAM|data\\s+(?:platform|warehouse|pipeline|engineering|analytics|migration)|machine\\s+learning|artificial\\s+intelligence\\s+(?:platform|systems?|solutions?|applications?)|AI\\s+(?:platform|systems?|solutions?|applications?)|enterprise\\s+(?:applications?|systems?|platforms?)|systems?\\s+integration|IT\\s+(?:systems?|infrastructure|applications?|delivery|projects?|programs?|solutions?)|digital\\s+(?:platform|systems?|solutions?|transformation)|cloud\\s+(?:platform|infrastructure|migration|services?|solutions?|applications?|systems?|technology)|network\\s+(?:infrastructure|systems?|technology)|information\\s+technology|access\\s+control|video\\s+surveillance|alarm\\s+systems?|informatique|infonuagique|intelligence\\s+artificielle\\s+(?:plateforme|syst[eè]mes?|solutions?|applications?)|cybers[eé]curit[eé]|donn[eé]es\\s+(?:plateforme|entrep[oô]t|pipeline|analytique|migration)|syst[eè]mes?\\s+(?:d['’]information|informatiques?|d['’]entreprise)|technologies?\\s+de\\s+l['’]information|infrastructure\\s+TI|contr[oô]le\\s+d['’]acc[eè]s|vid[eé]osurveillance|syst[eè]mes?\\s+d['’]alarme|r[eé]seaux?\\s+(?:informatiques?|de\\s+t[eé]l[eé]communications))\\b|\\b(?:implement(?:ation|s|ed|ing)?|deploy(?:ment|s|ed|ing)?|migrat(?:ion|e|es|ed|ing)|integrat(?:ion|e|es|ed|ing)|moderniz(?:ation|e|es|ed|ing)|deliver(?:y|s|ed|ing)?|roll[ -]?out|go-live|build(?:s|ing)?|architect(?:ure|s|ed|ing)?|configur(?:ation|e|es|ed|ing)|mise\\s+en\\s+[oœ]uvre|implant(?:ation|er|e)|d[eé]ploiement|migration|int[eé]gration|modernisation|livr(?:aison|er|e))\\b.{0,140}\\b(?:software(?:\\s+applications?)?|technology\\s+platforms?|cloud\\s+infrastructure|APIs?|logiciels?|syst[eè]mes?\\s+informatiques?|r[eé]seaux?\\s+informatiques?)\\b|\\b(?:software(?:\\s+applications?)?|technology\\s+platforms?|cloud\\s+infrastructure|APIs?|logiciels?|syst[eè]mes?\\s+informatiques?|r[eé]seaux?\\s+informatiques?)\\b.{0,140}\\b(?:implement(?:ation|s|ed|ing)?|deploy(?:ment|s|ed|ing)?|migrat(?:ion|e|es|ed|ing)|integrat(?:ion|e|es|ed|ing)|moderniz(?:ation|e|es|ed|ing)|deliver(?:y|s|ed|ing)?|roll[ -]?out|go-live|build(?:s|ing)?|architect(?:ure|s|ed|ing)?|configur(?:ation|e|es|ed|ing)|mise\\s+en\\s+[oœ]uvre|implant(?:ation|er|e)|d[eé]ploiement|migration|int[eé]gration|modernisation|livr(?:aison|er|e))\\b)).*\\Z",
    "(?sx)\\A(?:(?=.*\\b(?:professional\\s+services\\s+projects?|projets?\\s+des\\s+services\\s+professionnels)\\b)(?=.*\\b(?:software|cloud|technology|technologie|infonuagique|IT|TI)\\b)|(?=.*\\bmanage\\b.{0,120}\\bdevelopment\\s+project\\s+phases?\\b)(?=.*\\b(?:implementation|production\\s+start-up)\\b)(?=.*\\b(?:engineering|automated\\s+production)\\b)|(?=.*\\b(?:lead|support)\\b.{0,140}\\b(?:internal|external)\\s+projects?\\b)(?=.*\\b(?:robotics?|applied\\s+AI|artificial\\s+intelligence)\\b)(?=.*\\b(?:scope\\s+changes?|client\\s+requirements?|variation\\s+orders?)\\b))",
    "(?sx)\\A(?:(?=.*\\b(?:design|develop|operate|own|maintain|implement)(?:s|ed|ing)?\\b.{0,140}\\b(?:CI/CD|continuous\\s+integration|deployment|build|publishing)\\s+(?:tools?|pipelines?)\\b)(?=.*\\b(?:cloud\\s+environments?|infrastructure|network\\s+and\\s+server\\s+systems?|observability)\\b)|(?=.*\\b(?:design|build|oversee|lead)(?:s|ed|ing)?\\b.{0,140}\\b(?:data|reporting)\\s+pipelines?\\b)(?=.*\\b(?:analytics?\\s+platforms?|data\\s+models?|SQL|genomic|clinical\\s+data|business\\s+intelligence)\\b))",
    "(?sx)\\A(?=.*\\b(?:systems?\\s+integration|technology)\\s+programs?\\b)(?=.*\\bintegrated\\s+project\\s+plans?\\b)(?=.*\\bcritical\\s+path\\b)(?=.*\\bmilestones?\\b)(?=.*\\b(?:RAID|risks?|issues?|dependencies)\\b)"
  ],
  "title_blocklist": [
    "(?x)\\A\\s*(?!.*\\b(?:projects?|program(?:me)?s?|delivery|implementation|automation|platforms?|projets?|livraison|implantation|automatisation|plateformes?)\\b)(?:(?:senior|principal|technical|technique)\\s+)*(?:responsable\\s+de\\s+produit|propri[eé]taire\\s+du\\s+produit)\\b.*\\Z",
    "\\A\\s*(?:(?:senior|sr\\.?)\\s+)?sales\\s+program\\s+manager\\s*\\Z",
    "(?x)\\A(?=.*\\b(?:project|projects|projet|projets|g[eé]rant|charg[eé])\\b)(?=.*\\b(?:construction|civil|municipal|roadways?|transportation\\s+engineering|mechanical\\s+engineering|land\\s+development|powerline|electrical\\s+infrastructure|environmental|environnement|[eé]tudes?\\s+d['’]impacts?)\\b).*\\Z",
    "\\A\\s*(?:(?:senior|sr\\.?)\\s+)?manager\\s*-\\s*technology risk services(?:\\s*-\\s*IT assurance)?\\s*\\Z"
  ],
  "title_entry_level_blocklist": [],
  "title_include": [
    "(?x)\\b(?:(?:(?:technical|technology|information\\s+technology|digital|software|cloud|data\\s+center|cybersecurity|systems?|infrastructure|network)\\s+)+(?:project|program|delivery|implementation)(?:\\s+(?:project|program|delivery|implementation))?\\s+(?:manager|lead|director)|(?:IT|SaaS|ERP)\\s+(?:project|program|delivery|implementation)(?:\\s+(?:project|program|delivery|implementation))?\\s+(?:manager|lead|director)|(?:project|program|delivery|implementation)\\s+(?:manager|lead|director)(?:\\s*[-,(/]\\s*|\\s+)(?:IT|technical|technology|SaaS|ERP|cloud|data\\s+center|cybersecurity|systems?|infrastructure|network)|(?:chef|charg[eé](?:\\(e\\)|[·.]e)?|gestionnaire|directeur(?:\\(-?trice\\))?)(?:\\s+de|\\s+des)?\\s+projets?[^\\n|]{0,80}\\b(?:informatique|TI|technolog(?:ie|ique)|cybers[eé]curit[eé]|r[eé]seaux?|syst[eè]mes?|infrastructure)\\b)",
    "(?x)\\b(?:(?:solution|cloud\\s+data|AI|enterprise\\s+AI|technology)\\s+architect|solutions?\\s+designer|(?:SAP|Salesforce|ServiceNow|Workday|Dynamics(?:\\s*365)?|NetSuite|Veeva|SailPoint|monday\\.com)\\b.{0,50}\\b(?:consultant|lead|architect|administrator)|DevOps\\s+manager|forward\\s+deploy(?:ed|ment)\\s+(?:engineer|engineering)(?:\\s+manager)?|cloud\\s+administrator\\b.{0,40}\\b(?:Azure|AWS|GCP)|IT\\s+systems?\\s+analyst)\\b",
    "(?x)\\b(?:(?:machine\\s+learning|ML)\\s+(?:software\\s+)?engineer|software\\s+engineering\\s+manager|(?:web|software)\\s+developer|(?:senior|lead|principal|staff)\\s+developer|premi(?:er|[eè]re)\\s+d[eé]veloppeu(?:r|se)|(?:I\\.?T\\.?\\s*/\\s*network|platform\\b.{0,40}\\bnetwork)\\s+specialist|infrastructure\\s+reliability\\b.{0,30}\\b(?:specialist|engineer)|tools?\\s+and\\s+flows?\\s+applications?\\s+engineer|business\\s+intelligence\\s+manager|senior\\s+consultant\\b.{0,50}\\b(?:SailPoint|ServiceNow|Salesforce|SAP|Workday|Dynamics(?:\\s*365)?)|(?:senior\\s+)?project\\s+manager\\b.{0,60}\\bpayments?\\s+modernization|sp[eé]cialiste\\b.{0,100}\\b(?:syst[eè]mes?\\s+de\\s+gestion\\s+d['’]actifs\\s+num[eé]riques|syst[eè]mes?\\b.{0,50}\\bflux\\s+de\\s+travail))\\b",
    "(?x)\\b(?:(?:senior|sr\\.?|executive|associate)\\s+)*(?:director|head|manager|lead)\\s*(?:,\\s*|\\s+(?:of|for)\\s+)?(?:enterprise\\s+)?(?:application|app)\\s+(?:development\\s+)?delivery\\b"
  ]
}
```

### `ai_workflow_automation` final evaluator profile

```json
{
  "company_blocklist": [],
  "desc_blocklist": [],
  "description_include": [
    "(?is)\\A(?=.*(?:\\b(?:artificial intelligence|intelligence artificielle|intelligence artificiel|generative[ -]?AI|GenAI|IA g[eé]n[eé]rative|large language models?|LLMs?|retrieval[- ]augmented generation|RAG|agentic(?:[ -]?AI)?|AI agents?|agents? IA|Copilot(?: Studio)?|Agentforce|LangChain|LangGraph|LlamaIndex|Semantic Kernel|CCAI|Vertex AI|Azure AI|Amazon Bedrock|Model Context Protocol|MCP)\\b.{0,150}\\b(?:AI[- ](?:powered|enabled|driven) (?:workflows?|automation|processes?|operations?|routing)|agentic workflows?|agent orchestration|multi[- ]agent|tool (?:use|calling)|function calling|human[- ]in[- ]the[- ]loop|virtual agents?|agents? virtuels?|assistants? (?:IA|AI)|conversational flows?|flux conversationnels?|intelligent automation|automatisation intelligente|decision automation|intelligent routing|autonomous operations|RPA|n8n|Zapier|Make[.]com|Power Automate|UiPath|(?:API|system|enterprise|third-party|application) integrations?|int[eé]grations? (?:API|syst[eè]me|application)|flux de travail|business processes?|processus (?:d.affaires|m[eé]tier)|automatisation|orchestration)\\b|\\b(?:AI[- ](?:powered|enabled|driven) (?:workflows?|automation|processes?|operations?|routing)|agentic workflows?|agent orchestration|multi[- ]agent|tool (?:use|calling)|function calling|human[- ]in[- ]the[- ]loop|virtual agents?|agents? virtuels?|assistants? (?:IA|AI)|conversational flows?|flux conversationnels?|intelligent automation|automatisation intelligente|decision automation|intelligent routing|autonomous operations|RPA|n8n|Zapier|Make[.]com|Power Automate|UiPath|(?:API|system|enterprise|third-party|application) integrations?|int[eé]grations? (?:API|syst[eè]me|application)|flux de travail|business processes?|processus (?:d.affaires|m[eé]tier)|automatisation|orchestration)\\b.{0,150}\\b(?:artificial intelligence|intelligence artificielle|intelligence artificiel|generative[ -]?AI|GenAI|IA g[eé]n[eé]rative|large language models?|LLMs?|retrieval[- ]augmented generation|RAG|agentic(?:[ -]?AI)?|AI agents?|agents? IA|Copilot(?: Studio)?|Agentforce|LangChain|LangGraph|LlamaIndex|Semantic Kernel|CCAI|Vertex AI|Azure AI|Amazon Bedrock|Model Context Protocol|MCP)\\b))(?=.*(?:\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing)|architect(?:s|ed|ing)?|deploy(?:s|ed|ing)?|operationaliz(?:e|es|ed|ing)|productioniz(?:e|es|ed|ing)|configur(?:e|es|ed|ing)|program(?:s|med|ming)?|cod(?:e|es|ed|ing)|automat(?:e|es|ed|ing)|design(?:s|ed|ing)?|creat(?:e|es|ed|ing)|deliver(?:s|ed|ing)?|engineer(?:s|ed|ing)?|ship(?:s|ped|ping)?|constru(?:ire|it|isent)|d[eé]velopp(?:er|e|[eé]e?s?|ant)|impl[eé]ment(?:er|e|[eé]e?s?|ant)|int[eé]gr(?:er|e|[eé]e?s?|ant)|architectur(?:er|e|[eé]e?s?|ant)|d[eé]ploi(?:er|e|[eé]e?s?|ant)|con[cç](?:oit|evoir|u)|cr[eé](?:er|e|[eé]e?s?|ant)|livr(?:er|e|[eé]e?s?|ant)|programm(?:er|e|[eé]e?s?|ant)|automatis(?:er|e|[eé]e?s?|ant))\\b.{0,180}\\b(?:artificial intelligence|intelligence artificielle|intelligence artificiel|generative[ -]?AI|GenAI|IA g[eé]n[eé]rative|large language models?|LLMs?|retrieval[- ]augmented generation|RAG|agentic(?:[ -]?AI)?|AI agents?|agents? IA|Copilot(?: Studio)?|Agentforce|LangChain|LangGraph|LlamaIndex|Semantic Kernel|CCAI|Vertex AI|Azure AI|Amazon Bedrock|Model Context Protocol|MCP)\\b|\\b(?:artificial intelligence|intelligence artificielle|intelligence artificiel|generative[ -]?AI|GenAI|IA g[eé]n[eé]rative|large language models?|LLMs?|retrieval[- ]augmented generation|RAG|agentic(?:[ -]?AI)?|AI agents?|agents? IA|Copilot(?: Studio)?|Agentforce|LangChain|LangGraph|LlamaIndex|Semantic Kernel|CCAI|Vertex AI|Azure AI|Amazon Bedrock|Model Context Protocol|MCP)\\b.{0,180}\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing)|architect(?:s|ed|ing)?|deploy(?:s|ed|ing)?|operationaliz(?:e|es|ed|ing)|productioniz(?:e|es|ed|ing)|configur(?:e|es|ed|ing)|program(?:s|med|ming)?|cod(?:e|es|ed|ing)|automat(?:e|es|ed|ing)|design(?:s|ed|ing)?|creat(?:e|es|ed|ing)|deliver(?:s|ed|ing)?|engineer(?:s|ed|ing)?|ship(?:s|ped|ping)?|constru(?:ire|it|isent)|d[eé]velopp(?:er|e|[eé]e?s?|ant)|impl[eé]ment(?:er|e|[eé]e?s?|ant)|int[eé]gr(?:er|e|[eé]e?s?|ant)|architectur(?:er|e|[eé]e?s?|ant)|d[eé]ploi(?:er|e|[eé]e?s?|ant)|con[cç](?:oit|evoir|u)|cr[eé](?:er|e|[eé]e?s?|ant)|livr(?:er|e|[eé]e?s?|ant)|programm(?:er|e|[eé]e?s?|ant)|automatis(?:er|e|[eé]e?s?|ant))\\b))(?=.*(?:\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing)|architect(?:s|ed|ing)?|deploy(?:s|ed|ing)?|operationaliz(?:e|es|ed|ing)?|productioniz(?:e|es|ed|ing)?|configur(?:e|es|ed|ing)|program(?:s|med|ming)?|cod(?:e|es|ed|ing)|automat(?:e|es|ed|ing)|design(?:s|ed|ing)?|creat(?:e|es|ed|ing)|deliver(?:s|ed|ing)?|engineer(?:s|ed|ing)?|ship(?:s|ped|ping)?|constru(?:ire|it|isent)|d[eé]velopp(?:er|e|[eé]e?s?|ant)|impl[eé]ment(?:er|e|[eé]e?s?|ant)|int[eé]gr(?:er|e|[eé]e?s?|ant)|architectur(?:er|e|[eé]e?s?|ant)|d[eé]ploi(?:er|e|[eé]e?s?|ant)|con[cç](?:oit|evoir|u)|cr[eé](?:er|e|[eé]e?s?|ant)|livr(?:er|e|[eé]e?s?|ant)|programm(?:er|e|[eé]e?s?|ant)|automatis(?:er|e|[eé]e?s?|ant))\\b.{0,180}\\b(?:AI[- ](?:powered|enabled|driven) (?:workflows?|automation|processes?|operations?|routing)|agentic workflows?|agent orchestration|multi[- ]agent|tool (?:use|calling)|function calling|human[- ]in[- ]the[- ]loop|virtual agents?|agents? virtuels?|assistants? (?:IA|AI)|conversational flows?|flux conversationnels?|intelligent automation|automatisation intelligente|decision automation|intelligent routing|autonomous operations|RPA|n8n|Zapier|Make[.]com|Power Automate|UiPath|(?:API|system|enterprise|third-party|application) integrations?|int[eé]grations? (?:API|syst[eè]me|application)|flux de travail|business processes?|processus (?:d.affaires|m[eé]tier)|automatisation|orchestration)\\b|\\b(?:AI[- ](?:powered|enabled|driven) (?:workflows?|automation|processes?|operations?|routing)|agentic workflows?|agent orchestration|multi[- ]agent|tool (?:use|calling)|function calling|human[- ]in[- ]the[- ]loop|virtual agents?|agents? virtuels?|assistants? (?:IA|AI)|conversational flows?|flux conversationnels?|intelligent automation|automatisation intelligente|decision automation|intelligent routing|autonomous operations|RPA|n8n|Zapier|Make[.]com|Power Automate|UiPath|(?:API|system|enterprise|third-party|application) integrations?|int[eé]grations? (?:API|syst[eè]me|application)|flux de travail|business processes?|processus (?:d.affaires|m[eé]tier)|automatisation|orchestration)\\b.{0,180}\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing)|architect(?:s|ed|ing)?|deploy(?:s|ed|ing)?|operationaliz(?:e|es|ed|ing)?|productioniz(?:e|es|ed|ing)?|configur(?:e|es|ed|ing)|program(?:s|med|ming)?|cod(?:e|es|ed|ing)|automat(?:e|es|ed|ing)|design(?:s|ed|ing)?|creat(?:e|es|ed|ing)|deliver(?:s|ed|ing)?|engineer(?:s|ed|ing)?|ship(?:s|ped|ping)?|constru(?:ire|it|isent)|d[eé]velopp(?:er|e|[eé]e?s?|ant)|impl[eé]ment(?:er|e|[eé]e?s?|ant)|int[eé]gr(?:er|e|[eé]e?s?|ant)|architectur(?:er|e|[eé]e?s?|ant)|d[eé]ploi(?:er|e|[eé]e?s?|ant)|con[cç](?:oit|evoir|u)|cr[eé](?:er|e|[eé]e?s?|ant)|livr(?:er|e|[eé]e?s?|ant)|programm(?:er|e|[eé]e?s?|ant)|automatis(?:er|e|[eé]e?s?|ant))\\b))",
    "(?is)\\A(?=.*\\bproduction .{0,30}(?:LLM|agentic|AI).{0,30}systems?\\b)(?=.*\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing)|architect(?:s|ed|ing)?|deploy(?:s|ed|ing)?|operationaliz(?:e|es|ed|ing)|productioniz(?:e|es|ed|ing)|configur(?:e|es|ed|ing)|program(?:s|med|ming)?|cod(?:e|es|ed|ing)|automat(?:e|es|ed|ing)|design(?:s|ed|ing)?|creat(?:e|es|ed|ing)|deliver(?:s|ed|ing)?|engineer(?:s|ed|ing)?|ship(?:s|ped|ping)?)\\b)(?=.*\\b(?:tasks?|real users?|business outcomes?|systems? of record|client engagements?|applications?|solutions?)\\b)",
    "(?is)\\A(?=.*\\b(?:natural language processing|NLP)\\b)(?=.*\\bintelligent automation\\b)(?=.*\\bautomat(?:e|es|ed|ing)\\b.{0,120}\\b(?:document analysis|customer interactions?|business processes?)\\b)(?=.*\\b(?:design|develop|implement|deploy)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\b(?:generative[ -]?AI|GenAI)\\b)(?=.*\\b(?:integrat(?:ion|e|es|ed|ing) (?:of )?AI capabilities?|GenAI (?:products?|applications?|platforms?|services?) and process improvements?)\\b)(?=.*\\b(?:design(?:s|ed|ing)?|develop(?:s|ed|ing)?|deploy(?:s|ed|ing)?|deliver(?:s|ed|ing)?|implement(?:s|ed|ing)?|build(?:s|ing)?|built)\\b)",
    "(?is)\\A(?=.*\\b(?:AI agents?|agentic[ -]?AI|LLMs?)\\b)(?=.*\\b(?:agents? (?:take|takes|execute|executes|perform|performs|run|runs) (?:real |business |operational )?actions?|actions? on behalf of (?:a )?(?:real )?business)\\b)(?=.*\\b(?:build(?:s|ing)?|built|develop(?:s|ed|ing)?|implement(?:s|ed|ing)?|architect(?:s|ed|ing)?|ship(?:s|ped|ping)?)\\b)",
    "(?is)\\A(?=.*\\bAI[- ]assisted workflows?\\b)(?=.*\\binternal (?:tools?|tooling|libraries)\\b)(?=.*(?:\\b(?:build|develop|implement|create)(?:s|ed|ing)?\\b.{0,160}\\bAI[- ]assisted workflows?\\b|\\bAI[- ]assisted workflows?\\b.{0,160}\\b(?:build|develop|implement|create)(?:s|ed|ing)?\\b))",
    "(?is)\\A(?=.*\\bLLMs?\\b)(?=.*\\b(?:agent loops?|tool[- ]calling)\\b)(?=.*\\b(?:own|build|develop|design|implement|ship)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\b(?:AI[- ]driven security capabilities|LLM security|AI agents?)\\b)(?=.*\\b(?:automated remediation|security processes?|security workflows?)\\b)(?=.*\\b(?:develop|implement|integrate|deploy|automate)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\bAI/ML pipeline\\b)(?=.*\\b(?:automation|automatisations?|automated (?:tooling|processing|postprocessing))\\b)(?=.*\\b(?:build|develop|implement|create)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\b(?:agentic[ -]?AI|AI[- ]powered|LLM[- ]powered)\\b.{0,80}\\bworkflows?\\b)(?=.*(?:\\b(?:build|develop|implement|integrate|architect|deploy|create|deliver|lead)(?:s|ed|ing)?\\b.{0,180}\\b(?:agentic[ -]?AI|AI[- ]powered|LLM[- ]powered)\\b.{0,80}\\bworkflows?\\b|\\b(?:agentic[ -]?AI|AI[- ]powered|LLM[- ]powered)\\b.{0,80}\\bworkflows?\\b.{0,180}\\b(?:build|develop|implement|integrate|architect|deploy|create|deliver|lead)(?:s|ed|ing)?\\b))",
    "(?is)\\A(?=.*\\b(?:AI|GenAI|generative AI) solutions? and automation workflows?\\b)(?=.*\\b(?:develop|deploy|implement|build)(?:s|ed|ing)?\\b)(?=.*\\bbusiness (?:use cases?|processes?|outcomes?)\\b)",
    "(?is)\\A(?=.*\\bAI[- ]enabled solutions?\\b)(?=.*\\b(?:operational workflows?|decision[- ]making|operational efficienc(?:y|ies)|business outcomes?)\\b)(?=.*\\b(?:design|implement|deliver|deploy)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\b(?:LLM[- ]assisted (?:flows?|automation)|agentic systems?)\\b)(?=.*\\b(?:CAD|EDA|design) flows?\\b)(?=.*\\b(?:develop|integrate|implement|build|design)(?:s|ed|ing)?\\b)",
    "(?is)\\A(?=.*\\bAI[- ]powered applications?\\b)(?=.*\\bintelligent automation\\b)(?=.*\\b(?:design|develop|implement|build|deliver)(?:s|ed|ing)?\\b)(?=.*\\b(?:business (?:insights?|processes?|problems?|outcomes?)|enterprise (?:systems?|knowledge|applications?))\\b)"
  ],
  "title_blocklist": [
    "^(?:senior\\s+)?control systems?(?:\\s+software)?\\s+(?:designer|technologist|engineer)$",
    "^Expert Opportunity\\b"
  ],
  "title_entry_level_blocklist": [],
  "title_include": [
    "^(?=.*\\b(?:agentic(?:[ -]?AI)?|AI[ -]?agents?)\\b)(?=.*\\b(?:architect|engineer|developer)\\b).+$",
    "^(?=.*\\b(?:AI|artificial intelligence|intelligence artificielle|IA)\\b)(?=.*\\b(?:solutions?|workflow|automation|automatisation)\\b)(?=.*\\b(?:architect|engineer|developer|d[eé]veloppeur|ing[eé]nieur)\\b).+$",
    "\\b(?:Agentforce|Copilot Studio)\\s+(?:architect|engineer|developer)\\b"
  ]
}
```

## Final population impact

| Lane | Population | Included | Review | Filtered |
|---|---:|---:|---:|---:|
| `technology_delivery` | 6728 | 3402 | 3154 | 172 |
| `ai_workflow_automation` | 1620 | 485 | 1123 | 12 |

Complete stored-to-final transition counts, including unchanged rows, are at `linkedin-targeted-filter-impact-2026-09-09.json#/final_population_impact`.

## Sentinel replay

Relevant and borderline outcomes are reported separately.

| Lane | Relevant included | Relevant rate | Borderline included | Borderline review | Borderline filtered |
|---|---:|---:|---:|---:|---:|
| `technology_delivery` | 78/78 | 100.0% | 13 | 32 | 0 |
| `ai_workflow_automation` | 65/65 | 100.0% | 13 | 22 | 0 |

Every sentinel row, label, available rationale, source observation, stored status, final status, and matched rule is at `linkedin-targeted-filter-impact-2026-09-09.json#/full_sentinel_replay`. Current targeted and exclusion-recall labels provide rationales. Prior-audit rows provide labels but no rationale field; these are explicitly marked `not_present_in_prior_source` rather than reconstructed.

The sole cross-source label conflict is job `4445258802`: prior `clearly_irrelevant`, current targeted `borderline`. Current targeted coding takes precedence. Full observations are at `linkedin-targeted-filter-impact-2026-09-09.json#/canonical_label_conflicts`.

## Backfill evidence

`linkedin-targeted-backfill-dry-run-2026-09-09.json` is byte-for-byte and parsed-JSON equal to `revision-10-backfill-dry-run-before-migration.json`. Both SHA-256 values are `c963997adbea5fe0e8e42139cab9f7104d159b9349fb46d6c97cc2c6e086fc3e`. It scans 8,348 memberships, reports 3,502 changes, applies 0 changes, and targets revision 10.

| Transition | Count |
|---|---:|
| `filtered->filtered` | 119 |
| `filtered->included` | 108 |
| `filtered->review` | 251 |
| `included->filtered` | 51 |
| `included->review` | 2760 |
| `pending->included` | 12 |
| `pending->review` | 40 |
| `review->filtered` | 14 |
| `review->included` | 147 |

The dry-run artifact retains every change object at `/changes/0` through `/changes/3501`. A complete row index with lane, job ID, old/new status, and an exact file-plus-JSON-Pointer for every row is at `linkedin-targeted-filter-impact-2026-09-09.json#/backfill_dry_run/change_row_pointers`.

`linkedin-targeted-backfill-apply-2026-09-09.json` is byte-for-byte and parsed-JSON equal to `revision-10-backfill-apply.json`. Both SHA-256 values are `fc2c9b25dc5ce26c04a8cf564eb4f36ee044c75ae21203c684fc7be862faa2b7`. It scans all 8,348 target memberships and applies all 3,502 changes predeclared by the dry run, with the same transition counts shown above.

`linkedin-targeted-backfill-second-dry-run-2026-09-09.json` is byte-for-byte and parsed-JSON equal to `revision-10-backfill-second-dry-run.json`. Both SHA-256 values are `5df939b73425e58dfc7f413f6d75affcd6949afe1c02026e3cf6808ba8c7855f`. It scans all 8,348 target memberships, reports zero changes, and applies zero changes, confirming the applied backfill reached the declared revision 10 state.

## Limitations

- Coding was model-assisted independent single coding, not human double coding; no inter-rater reliability or human adjudication is available.
- Stored current filter_status and filter_reason are operational state, not ground-truth labels; the filtered guard itself found false exclusions.
- Strata overlap: 325 draws represent 307 unique lane/job IDs. Do not pool strata as independent observations.
- Wilson 95% intervals are per-stratum binomial intervals for relevant plus borderline among decided labels; insufficient labels are excluded, finite-population correction and coding error are not modeled.
- Sole-query yields are descriptive marginal samples, not causal query estimates; query associations are non-exclusive. No query removal is recommended.
- The snapshot covers LinkedIn Canada memberships present in the frozen population and active-query provenance observed at or after revision 9; it does not estimate other providers, geographies, missing listings, or future drift.
- Complete title exclusion match sets were replayed on the supplied 8,348-row population. Most large match sets received deterministic recall samples rather than exhaustive relevance coding.
- The stored technology candidate pattern-1 match-set artifact has 118 rows, while replay on the supplied later 8,348-row population has 119 due to one added title, Technical Product Manager - GenAI Programmes. Both snapshots are retained rather than silently reconciled.
- The revision-5 rollback identifier is recovered, but its configuration body is absent from the supplied evidence.
- Prior-audit label rows do not contain rationales; these are marked not_present_in_prior_source rather than reconstructed or invented.
- Backfill evidence is point-in-time: the first dry run predeclared the changes, the apply artifact records all 3,502 applied changes, and the second dry run records zero residual changes. Production state may drift after the final snapshot.

## Reproducibility map

- Frozen revision, active queries, exact sample IDs, labels/rationales, jobs, and provenance: `linkedin-targeted-relevance-samples-2026-09-09.json`.
- Wilson results, role-family clusters, query attribution, exact filter changes, complete exclusion match sets/title counts, manual recall rows/verdicts, rejected patterns, population transitions, sentinel replay, and row pointers: `linkedin-targeted-filter-impact-2026-09-09.json`.
- Exact no-write migration preview and every changed row: `linkedin-targeted-backfill-dry-run-2026-09-09.json`.
- Exact production apply result and every changed row: `linkedin-targeted-backfill-apply-2026-09-09.json`.
- Exact post-apply no-write verification: `linkedin-targeted-backfill-second-dry-run-2026-09-09.json`.
- SHA-256 and byte-size manifest for every supplied source used: `linkedin-targeted-filter-impact-2026-09-09.json#/source_manifest`.

Validation replays all 11 deterministic strata, checks all sample/label key sets and non-empty supplied rationales, compiles final regexes, evaluates all 8,348 rows, reconciles title match sets, verifies recall sample/label equality, verifies 100% relevant inclusion and zero borderline filtering, parses all output JSON files, enforces ASCII-only JSON, and verifies source-to-deliverable byte and parsed-JSON equality for the dry-run, apply, and second-dry-run artifacts.
