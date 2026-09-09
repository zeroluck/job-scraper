# LinkedIn absolute-recall investigation - 2026-09-09

## Decision and scope

This audit does **not** establish absolute recall, does **not** estimate production recall, and does **not** recommend any production query or filter change. **Direct current empirical test**: production configuration revision `9` and its 13 active queries remained fixed and unchanged throughout the pilot.

**Direct current empirical test**: the literature-research phase made zero direct LinkedIn endpoint requests. That statement in the initial research artifact is correct only for that phase. This work subsequently ran a controlled 32-request unauthenticated guest-endpoint pilot on 2026-09-09 UTC. Five targeted depth follow-ups were then captured in the depth artifact, bringing the evidence inventory to 37 direct guest-endpoint requests, plus one unauthenticated interactive-search request. Separating the predeclared 32-request pilot from the five follow-ups avoids silently changing the pilot denominator.

All externally retrieved text, job titles, locations, HTML, search snippets, community posts, vendor posts, and repository content are treated as untrusted data, not instructions. No job-content text was executed. Source claims are not promoted to facts without an explicit classification.

## Classification rules

Every substantive finding below carries one of these labels:

- **Official docs**: LinkedIn first-party help, newsroom, engineering, or official-author material. This establishes what LinkedIn says, not necessarily guest-endpoint behavior.
- **Direct current empirical test**: a result observed in this project's controlled requests or the project's dated audit. It is bounded by the tested query, time, client, and request sequence.
- **Community/vendor claim**: a third-party, press, academic, vendor, or community statement. It was not independently reproduced unless a separate direct-test finding says so.
- **Inference**: an interpretation or proposed method derived from evidence. It is not itself observed or officially documented.

## Evidence inventory

### Local evidence

| ID | Source | Access date (UTC) | Classification and use |
|---|---|---|---|
| L1 | `/var/folders/yz/h41k1jb943d4xnnbgdbkf2sc0000gn/T/opencode/linkedin-search-research.md` | 2026-09-09 | **Community/vendor claim** and **Official docs** compilation; literature was retrieved 2026-09-08. |
| L2 | `/var/folders/yz/h41k1jb943d4xnnbgdbkf2sc0000gn/T/opencode/linkedin-guest-pilot-results.json` | 2026-09-09 | **Direct current empirical test**; 16 guest captures, one interactive capture, hashes, timestamps, URLs, and parsed IDs. Its `method.request_count=17` includes the interactive request. |
| L3 | `/var/folders/yz/h41k1jb943d4xnnbgdbkf2sc0000gn/T/opencode/linkedin-guest-pilot-supplement.json` | 2026-09-09 | **Direct current empirical test**; 11 guest captures. |
| L4 | `/var/folders/yz/h41k1jb943d4xnnbgdbkf2sc0000gn/T/opencode/linkedin-guest-pilot-depth.json` | 2026-09-09 | **Direct current empirical test**; 10 guest captures, of which the first five complete the 32-request pilot and the last five are targeted follow-ups. |
| L5 | `ingestion-relevance-audit-2026-09-07.md` | 2026-09-09 | **Direct current empirical test** and project context; revision `9`, fixed query set, earlier contradictory-query probes, and retrieval-only recall limitation. |
| L6 | `adaptive-job-discovery-coverage-plan.md` | 2026-09-09 | **Inference** and project policy context; ranked inventory, watermark, source-control, and authorization limitations. |
| L7 | `linkedin_source_policy.py` | 2026-09-09 | **Inference** embodied as operational policy; durable request gate and circuit behavior. |

**Direct current empirical test**: the research artifact labels its inventory as "30 sources," but its visible A-E tables contain 38 external rows, plus one internal row. This report does not rely on the stated count; it inventories the rows actually present.

### External literature inventory

All URLs in this table were accessed for the literature artifact on 2026-09-08 UTC unless an access exception is stated. Publication/update dates are source metadata reported in that artifact, not newly verified here.

| ID | Exact URL | Publication/update note | Classification |
|---|---|---|---|
| A1 | `https://www.linkedin.com/help/linkedin/answer/a507571/using-boolean-modifiers-when-searching-for-jobs-on-linkedin` | Undated; returned HTTP 404 on 2026-09-08, with content obtained from indexed metadata | **Official docs** |
| A2 | `https://www.linkedin.com/help/linkedin/answer/a6889044` | Reported updated about 2026-08-25 | **Official docs** |
| A3 | `https://news.linkedin.com/2026/Professional_Edge_Skills_Verified` | Published 2026-01-26 | **Official docs** |
| A4 | `https://www.linkedin.com/blog/engineering/ai/building-the-next-generation-of-job-search-at-linkedin` | Original May 2025; reported updated 2026-08-13 | **Official docs** |
| A5 | `https://www.linkedin.com/blog/engineering/search/reimagining-linkedins-search-stack` | Published 2026-01-21 | **Official docs** |
| A6 | `https://www.linkedin.com/blog/engineering/ai/semantic-search-for-ai-agents-at-scale-retrieval-and-ranking-for-linkedins-hiring-assistant` | Reported updated 2026-08-13 | **Official docs** |
| A7 | `https://news.linkedin.com/2026/LinkedIn-Research-Talent-2026` | Published 2026-01-07 | **Official docs** |
| B1 | `https://arxiv.org/abs/2602.07309` | Published 2026-02-07; LinkedIn-engineer authors | **Community/vendor claim** |
| B2 | `https://arxiv.org/html/2605.27441v2` | Published 2026-06-07; LinkedIn-engineer authors | **Community/vendor claim** |
| B3 | `https://venturebeat.com/infrastructure/inside-linkedins-generative-ai-cookbook-how-it-scaled-people-search-to-1-3` | Published 2025-11-13 | **Community/vendor claim** |
| C1 | `https://apiserpent.com/blog/linkedin-jobs-api-filters` | Published 2026-07-02 | **Community/vendor claim** |
| C2 | `https://browse.sh/skills/linkedin.com/search-linkedin-jobs-3v1wu7` | Undated; vendor reports five-query verification | **Community/vendor claim** |
| C3 | `https://github.com/ChocoData-com/linkedin-jobsearch-scraper` | Reported published 2026-07-20 | **Community/vendor claim** |
| C4 | `https://dev.to/apify/my-scraper-returned-660-jobs-there-were-880-nothing-in-the-output-said-so-3ck6` | Published 2026-09-01 | **Community/vendor claim** |
| C5 | `https://scraperly.com/scrape/linkedin-jobs` | Published 2025-06-01; reported updated in 2026 | **Community/vendor claim** |
| C6 | `https://clura.ai/blog/linkedin-scraper-python` | Published 2026-06-22 | **Community/vendor claim** |
| C7 | `https://www.practical.tools/blog/linkedin-jobs-scraper-no-login-guest-api-guide` | Published 2026-04-29 | **Community/vendor claim** |
| C8 | `https://apify.com/thescrappa/linkedin-jobs-search-scraper/api/openapi` | Undated, reported current in 2026 | **Community/vendor claim** |
| C9 | `https://apify.com/api-empire/linkedin-jobs-scraper/api` | Undated, reported current in 2026 | **Community/vendor claim** |
| C10 | `https://www.refolk.ai/blog/linkedin-recruiter-1000-cap-agentic-sourcing` | Published 2026-05-07 | **Community/vendor claim** |
| C11 | `https://www.scrapingdog.com/blog/scrape-linkedin-jobs/` | Published 2024-10-31; modified 2026-07-01 | **Community/vendor claim** |
| D1 | `https://dev.to/agenthustler/how-to-scrape-linkedin-job-listings-in-2026-python-public-api-no-login-required-5bin` | Published 2026-03-23 | **Community/vendor claim** |
| D2 | `https://dev.to/agenthustler/scraping-linkedin-job-listings-in-2026-public-data-without-login-3fnb` | Published 2026-03-20 | **Community/vendor claim** |
| D3 | `https://dev.to/agenthustler/what-you-can-do-with-linkedin-jobs-data-that-linkedins-own-ui-wont-let-you-m1f` | Published 2026-04-11; edited 2026-04-17 | **Community/vendor claim** |
| D4 | `https://github.com/speedyapply/JobSpy/issues/258` | Opened 2025-03-17; cited comment 2025-08-13 | **Community/vendor claim** |
| D5 | `https://www.trykondo.com/blog/linkedin-job-search-hacks` | Undated | **Community/vendor claim** |
| D6 | `https://github.com/felixskmarcio/linkedin-jobs-scraper` | Undated, reported current in 2026 | **Community/vendor claim** |
| D7 | `https://github.com/hendrixfreire/linkedin-job-scraper/blob/main/linkedin_jobs.py` | Undated, reported current in 2026 | **Community/vendor claim** |
| D8 | `https://github.com/colophon-group/jobseek/blob/143aa449/apps/crawler/src/core/monitors/linkedin.py` | Undated, commit-pinned URL | **Community/vendor claim** |
| D9 | `https://download.plaud.ai/ChocoData-com/linkedin-jobsearch-scraper` | Dated 2026-07-20 | **Community/vendor claim** |
| D10 | `https://explainx.ai/skills/linkedin.com/search-linkedin-jobs-3v1wu7/search-recent-jobs` | Undated; indexed date reported as 2024-03-19 | **Community/vendor claim** |
| D11 | `https://github.com/RamiAdell/job-hunter` | Undated, reported current in 2026 | **Community/vendor claim** |
| E1 | `https://www.fastcompany.com/91467930/linkedin-ai-powered-job-search` | Published 2026-01-07 | **Community/vendor claim** |
| E2 | `https://www.computerworld.com/article/4096076/how-linkedin-is-using-ai-to-improve-its-job-search-features.html` | Published 2025-11-26 | **Community/vendor claim** |
| E3 | `https://www.businessinsider.com/linkedin-ai-job-search-made-job-hunt-more-approachable-2025-5` | Published 2025-05-08 | **Community/vendor claim** |
| E4 | `https://www.socialmediatoday.com/news/linkedin-expands-ai-job-discovery-to-more-languages/809019/` | Published 2026-01-07 | **Community/vendor claim** |
| E5 | `https://www.linkedin.com/posts/erranberger_linkedin-is-expanding-its-ai-powered-job-activity-7414688704616677376-qXtl` | Published 2026-01-07; LinkedIn executive post | **Official docs** |
| E6 | `https://www.linkedin.com/posts/denisgorican_linkedin-quietly-changed-how-jobs-and-candidates-activity-7427026091086626816-i3R1` | Published 2026-02-10 | **Community/vendor claim** |
| P1 | `https://www.linkedin.com/help/linkedin/answer/a524335` | Accessed for project audit 2026-09-07 | **Official docs** |

## Pilot design and exact request surface

### Controlled variables

- **Direct current empirical test**: requests were unauthenticated, used a fixed user agent, no retries, no proxy rotation, and a nominal 1.5-second delay. The result artifact states this directly.
- **Direct current empirical test**: the primary narrow query was `AI solutions engineer LLM workflow integration`, Canada location text, Canada `geoId=101174742`, `f_TPR=r172800`, and usually `f_JT=F`.
- **Direct current empirical test**: the broad depth query was `software engineer`, Canada location text, `geoId=101174742`, `f_TPR=r604800`, and `f_JT=F`.
- **Direct current empirical test**: primary guest requests ran from `2026-09-09T05:01:55.671211+00:00` through `2026-09-09T05:04:42.963699+00:00`. Follow-ups ended at `2026-09-09T05:05:37.135928+00:00`.
- **Inference**: because requests were close in time and came from one client/network path, the pilot measures immediate local repeatability, not day-to-day determinism, personalization, regional behavior, or universal endpoint semantics.

### Exact URLs and variants

Base guest URL:

`https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`

**Direct current empirical test**: the raw JSON sources record the exact `final_url`, UTC timestamp, status, content type, byte count, SHA-256, parsed IDs, titles, and locations for every request. The complete tested URL set is reconstructible without ambiguity from these exact query strings and listed `start` values:

| Test | Exact URL/query string | Tested values | Classification |
|---|---|---|---|
| Narrow base | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=F&start=0` | Paired runs at `start=0,25,50`; additional `start=0,10,20,30`; depth `start=975,1000,1025` | **Direct current empirical test** |
| Interactive comparison | `https://www.linkedin.com/jobs/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Job type omitted | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&start=0` | `start=0` | **Direct current empirical test** |
| Contract | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=C&start=0` | `start=0` | **Direct current empirical test** |
| Remote | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=F&f_WT=2&start=0` | `start=0` | **Direct current empirical test** |
| On-site | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=F&f_WT=1&start=0` | `start=0` | **Direct current empirical test** |
| No `geoId` | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&f_TPR=r172800&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Date 24 hours | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r86400&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Date 7 days | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_TPR=r604800&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Date unset | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=AI+solutions+engineer+LLM+workflow+integration&location=Canada&geoId=101174742&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Boolean-shaped text | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=%22AI%22+AND+%22workflow%22&location=Canada&geoId=101174742&f_TPR=r172800&f_JT=F&start=0` | `start=0` | **Direct current empirical test** |
| Broad depth | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=software+engineer&location=Canada&geoId=101174742&f_TPR=r604800&f_JT=F&start=0` | `start=0,90,100,200,250,300,400,450,490,500,900,975,1000` across L3-L4 | **Direct current empirical test** |

`Accept-Language: en` and `Accept-Language: fr` were request-header variants of the narrow base URL; they were not different URLs.

## Search semantics, operators, and filters

### Search model

- **Official docs**: A2 and A4-A6 describe LinkedIn member search as intent-aware and semantic, combining query understanding, entity/taxonomy extraction, strict filters, embedding retrieval, and ranking. These documents do not document the guest endpoint as a supported API.
- **Official docs**: A1/P1 document uppercase `AND`, `OR`, `NOT`, quotation marks, and parentheses for LinkedIn interactive search, and say wildcard `*` and `+`/`-` are unsupported. A1 returned HTTP 404 when the literature artifact accessed it, so its current location/status is uncertain.
- **Community/vendor claim**: C1-C4 report that guest `keywords` behaves as fuzzy text, may weight title matches, and does not provide exhaustive stable pagination.
- **Direct current empirical test**: the Boolean-shaped query returned ten IDs and a different set from the narrow natural-language query.
- **Inference**: different IDs prove that changing query text changed retrieval/ranking in this request. They do not prove `AND` or quotation semantics, exact phrase enforcement, exclusion behavior, or equivalence with the interactive search syntax.
- **Direct current empirical test**: the 2026-09-07 project audit reports that contradictory guest queries such as `"Network Engineer" NOT "Network"` and additions such as `AND qzxxnonexistenttoken` still returned conflicting jobs.
- **Inference**: the combined evidence supports treating guest `keywords` as fuzzy retrieval for audit design. It is not enough to characterize its full grammar.

### Operators and filter surface

| Operator/filter | Evidence and status | Classification |
|---|---|---|
| `keywords` | Present in every pilot search; changing text changed one top-10 set. Match fields and weighting were not isolated. | **Direct current empirical test** |
| `location` | `location=Canada` was used. Omitting `geoId` retained the same ten IDs for this query. No alternate geography was tested. | **Direct current empirical test** |
| `geoId` | `geoId=101174742` was used. Vendor/community sources describe numeric geo targeting and sometimes prefer it to text. | **Direct current empirical test** for use; **Community/vendor claim** for general semantics |
| `start` | Returned 10-card fragments at many offsets, empty HTTP 200 fragments at some offsets, and HTTP 400 at `>=1000` in tested requests. | **Direct current empirical test** |
| `f_TPR` | `r86400`, `r172800`, `r604800`, and omission were tested; top-10 IDs differed among 24-hour, 7-day, and unset variants. | **Direct current empirical test** |
| `f_JT` | `F`, `C`, and omission produced the same ten IDs for this single narrow query at that time. | **Direct current empirical test** |
| `f_WT` | `1` and `2` produced the same ten IDs as the narrow baseline in this single query. | **Direct current empirical test** |
| `sortBy` | Vendors report `DD` and `R`; the pilot did not test it. | **Community/vendor claim** |
| `limit` | Vendors report a current maximum of ten; the pilot did not vary it. | **Community/vendor claim** |
| `f_E`, `f_C`, `f_AL`, `f_EA`, `f_I`, `f_F`, `f_PP`, `f_SB2`, `distance`, `currentJobId`, `refresh` | Reported by one or more vendor/community implementations; not tested here and mostly not officially documented for the guest endpoint. | **Community/vendor claim** |
| Experience/employment/remote filters in member search | A2 lists date, company, experience, employment type, remote, LinkedIn Apply, network, and applicant-count filters, while also describing filters still returning during rollout. | **Official docs** |
| Guest filter survival after the August 2026 search changes | C4 claims several legacy URL filters changed or ceased to map cleanly. | **Community/vendor claim** |

- **Inference**: identical IDs for `f_JT` and `f_WT` variants are compatible with ignored filters, cache/ranking behavior, parameter migration, or coincidental overlap. This one query does not prove that the filters are ignored.
- **Inference**: date-variant differences are evidence that the parameter or changed request affected retrieval, but without independently checking each posting timestamp they do not prove strict recency compliance.

## Determinism, pagination, and retrievable depth

### Repetition

- **Direct current empirical test**: paired captures at `start=0`, `25`, and `50` each returned ten IDs; for each offset the repeat had intersection `10`, Jaccard `1.0`, and identical order.
- **Direct current empirical test**: a later narrow `start=0` capture about two minutes after the paired run shared only 6 of the original 10 IDs. This is outside the immediate paired-repeat comparison but inside the same evidence set.
- **Inference**: the endpoint was perfectly repeatable over the immediate paired interval for this query and these offsets, but not stable across the entire pilot. Neither observation establishes general determinism or non-determinism rates.
- **Community/vendor claim**: C1, C3, C4, and D4/D8 report overlap, reordering, and unstable IDs across pagination or repeat runs. Those rates are not imported as this project's measured rates.

### Interactive comparison

- **Direct current empirical test**: the unauthenticated interactive URL returned HTTP 200 and the capture parser found 60 job IDs.
- **Direct current empirical test**: all ten IDs in the first guest `start=0` capture were contained in those 60 interactive IDs.
- **Inference**: this establishes containment for one near-contemporaneous request pair, not equality of the interactive and guest universes, ranking, filters, or maximum depth.

### Page size and offsets

- **Direct current empirical test**: every non-empty successful guest response in the pilot contained exactly ten parsed job cards. Ten-step offsets `0,10,20,30` each returned ten IDs.
- **Community/vendor claim**: current third-party reports describe 10-card responses and recommend increments of ten; older community code used 25. The paired `25` offsets in this pilot show that non-ten offsets can return cards, not that 25 is a correct exhaustive stride.
- **Inference**: no `totalResultCount` was observed in the captured fragments, but the pilot parser was designed around cards rather than a formal schema audit. Exhaustion cannot be inferred safely from a single empty page without repeat/neighbor checks.

### Caps and depth

- **Direct current empirical test**: the narrow query returned an empty HTTP 200 body fragment at `start=975`; `start=1000` and `1025` returned HTTP 400.
- **Direct current empirical test**: the broad query returned ten cards at `start=450`, but empty HTTP 200 fragments at `start=490` and `500`; it was also empty at `900` and `975`, and returned HTTP 400 at `1000`.
- **Inference**: for the broad query in this run, the observable transition supports query-specific retrievable depth somewhere after `450` and before or at `490`; colloquially, around `<500`. Because offsets were sparse and ranked retrieval may be discontinuous, this is not an exact count.
- **Inference**: `>=1000` HTTP 400 is an input-boundary observation. It does not prove that every query exposes 1,000 jobs or that 1,000 is the universal inventory cap.
- **Community/vendor claim**: C3, C4, C10, and other sources describe a roughly 1,000-result ceiling. The current pilot reproduced the HTTP 400 boundary but did not reproduce 1,000 retrievable results.

## Geography, work mode, date, and language

- **Direct current empirical test**: `location=Canada` with and without `geoId=101174742` returned the same ten IDs for the narrow query. All ten parsed locations in the baseline were Canadian strings.
- **Inference**: this supports correct-looking Canada behavior for one top page. It does not test city/country contrasts, IP effects, geo fallback, complete geographic inclusion, or false exclusions.
- **Community/vendor claim**: C2/D6 report that location and `geoId` can change scope; D3 claims regional failures outside major markets. These claims conflict in breadth and require a dedicated multi-region test.
- **Direct current empirical test**: `f_WT=1`, `f_WT=2`, and no work-type variant yielded the same ten IDs. Detail pages and actual work modes were not checked.
- **Inference**: no conclusion about work-mode filter correctness is available. Search-card location strings are not sufficient ground truth for remote/hybrid/on-site status.
- **Official docs**: A2 lists date posted as an available member-search filter.
- **Direct current empirical test**: the 24-hour, 7-day, and unset date variants returned different top-10 ID sets. Pairwise identity was not observed.
- **Inference**: the pilot shows a date-parameter effect, not strict boundary accuracy. A future test must compare source timestamps to a fixed UTC cutoff and distinguish original post, repost, and display-age semantics.
- **Official docs**: A2/A3 describe AI-powered member search in English, German, French, Spanish, and Portuguese.
- **Direct current empirical test**: changing only `Accept-Language` between English and French returned the same ten IDs for the English narrow query.
- **Inference**: this says only that the header did not alter this top page. It does not test French query understanding, French-title recall, UI locale, posting language, or multilingual indexing.

## Title-only and job-function support

- **Community/vendor claim**: C1/C2 say `keywords` searches more than title text with title weighting. C4 says a legacy title filter does not map cleanly to the newer search experience.
- **Inference**: no supported guest `title-only` parameter is established by this evidence. A title-looking keyword query is not a title-only query unless off-title matches are independently excluded.
- **Community/vendor claim**: D1-D3 and wrappers report `f_F`/function identifiers; C4 says these identifiers are not readily convertible in the newer search flow.
- **Official docs**: A2's listed current member-search filters do not include job function.
- **Direct current empirical test**: this pilot did not test `f_F`, a title parameter, title-only matching, or job-function compliance.
- **Inference**: title-only and job-function recall remain unresolved and must be evaluated as separate sentinel tests, not assumed from the general keyword pilot.

## Pilot funnel

### Full funnel schema

Each run should persist the following stages and denominators. Rates must name their denominator; no stage may silently substitute for another.

| Stage | Required fields | Metric |
|---|---|---|
| 0. External availability frame | `frame_revision`, employer, ATS, external source, external requisition ID, canonical URL, first/last observed UTC, lane eligibility label | `N_external_eligible` |
| 1. LinkedIn availability | LinkedIn job ID/URL independently located, first/last available UTC, evidence source, unavailable/unknown reason | `N_linkedin_available / N_external_eligible` |
| 2. Search retrieval | run/scope/query IDs, configuration revision, exact URL/headers class, requested UTC, offset, status, response hash, raw card count | `N_retrieved_source_ids / N_linkedin_available` |
| 3. Card parsing | card ordinal, raw LinkedIn ID/URL/title/company/location, parser version, parse status/error | `N_cards_parsed / N_cards_returned` |
| 4. Search deduplication | source ID, first/last scope, all query provenance, duplicate relation | `N_unique_source_ids / N_cards_parsed` |
| 5. Detail acquisition | source ID, request attempts, terminal status, HTTP class, response hash, required-field completeness | `N_detail_success / N_unique_source_ids_queued` |
| 6. Detail parsing | parser/schema version, title/company/location/description/post dates, parse status, missing fields | `N_detail_parsed / N_detail_success` |
| 7. Canonicalization | canonical job ID, normalized employer/title/location, requisition ID, ATS URL, match rule/confidence, collision/split status | `N_canonicalized / N_detail_parsed` |
| 8. Lane assignment | canonical job ID, lane, label source/version, relevant/borderline/irrelevant/unknown | `N_lane_eligible / N_canonicalized` |
| 9. Policy/filter outcome | membership ID, `included`/`review`/`filtered`/`pending`, rule and revision | status shares over `N_lane_eligible` |
| 10. Downstream completion | scoring/analysis/resume task IDs, claim/completion/error timestamps | `N_downstream_complete / N_included` |

### Metrics available from this pilot

| Funnel measure | Pilot result | Classification |
|---|---|---|
| External availability denominator | Unavailable; no employer/ATS frame existed. | **Direct current empirical test** |
| LinkedIn availability denominator | Unavailable; no independent LinkedIn-presence frame existed. | **Direct current empirical test** |
| Search-retrieval recall | Unavailable because both preceding denominators were absent. | **Inference** |
| Primary direct endpoint status | `29/32` HTTP 200; `3/32` HTTP 400. Of the HTTP 200 responses, 25 were standard non-empty 10-card fragments and 4 were empty depth fragments. | **Direct current empirical test** |
| Follow-up direct endpoint status | Five additional HTTP 200 captures: four 10-card fragments and one empty depth fragment. Full L2-L4 total: `34/37` HTTP 200 and `3/37` HTTP 400. | **Direct current empirical test** |
| Card parsing | `10/10` cards parsed for every successful standard response: 25/25 such responses in the primary pilot (`250/250` card positions) and 29/29 including follow-ups (`290/290`). Empty depth fragments had zero cards by definition. | **Direct current empirical test** |
| Interactive parsing | 60 IDs parsed from one HTTP 200 response. | **Direct current empirical test** |
| Production parser denominator | Unavailable; captures do not exercise or identify the production parser's full card/detail contract. | **Direct current empirical test** |
| Detail acquisition/parsing | Unavailable; no detail-endpoint funnel was run. | **Direct current empirical test** |
| Canonicalization | Unavailable; no pilot records traversed canonical matching. | **Direct current empirical test** |
| Lane/filter/downstream denominators | Unavailable; no pilot records traversed those stages. | **Direct current empirical test** |

**Inference**: HTTP 200 is transport success, not evidence of non-empty retrieval, relevance, filter compliance, or recall. HTTP 400 at deep offsets is not a parser failure.

## External-universe recall protocol

### Estimands and frozen revision

1. **Inference**: define the primary estimand per lane and geography as `R_external = externally eligible jobs retrieved by production search / all externally eligible jobs in the fixed frame`. This measures coverage against an external hiring universe, not "all LinkedIn jobs."
2. **Inference**: define the conditional estimand as `R_linkedin = externally eligible, independently verified LinkedIn-available jobs retrieved / externally eligible, independently verified LinkedIn-available jobs`. Report it separately because employers do not post every ATS job to LinkedIn.
3. **Inference**: freeze a UTC inclusion window `[T0,T1)`, geography taxonomy, lane rubric, source eligibility rule, canonicalization revision, parser revision, and production configuration revision before collection. Use revision `9` and the unchanged 13-query set for the first benchmark so the pilot context remains comparable.
4. **Inference**: assign a protocol revision and content hash. Any changed query, filter, lookback, parser, lane definition, employer sample, source, or canonicalization rule creates a new revision; do not pool revisions as one estimate.

### Employer and source frame

1. **Inference**: construct an employer panel stratified by ATS family (`Greenhouse`, `Lever`, `Workday`, `iCIMS`, `SmartRecruiters`, and custom/other), employer size, lane hiring volume, and target geography. Record selection probabilities or explicitly label a purposive panel.
2. **Inference**: independently enumerate live requisitions from employer-owned career sites or ATS feeds. Do not seed the panel from LinkedIn results. Preserve source URL, requisition ID, first/last observation, raw hash, and extraction status.
3. **Inference**: add at least one independent aggregator/index as a second discovery source. Record whether it republishes LinkedIn content; a LinkedIn-derived wrapper is not independent and must not be represented as such.
4. **Inference**: target at least 100 adjudicated eligible jobs per lane where feasible. For any reported subgroup, require `n>=30`; otherwise publish counts and mark the rate exploratory without a precision claim.
5. **Inference**: retain all sampled employers, including zero-job employers and failed ATS enumerations, to avoid survivorship bias. Report strata weights and both weighted and unweighted results.

### Eligibility and canonicalization

1. **Inference**: two reviewers should independently label lane eligibility from employer-owned title, description, location, employment type, and open/closed status under a frozen rubric. Resolve disagreements and retain `unknown` rather than forcing uncertain rows.
2. **Inference**: canonicalize first by stable employer requisition ID plus employer/ATS identity; then by normalized canonical ATS URL; then by a documented composite of employer, normalized title, normalized location, and posting/requisition evidence.
3. **Inference**: normalize URL scheme/host, tracking parameters, Unicode, whitespace, punctuation, corporate aliases, remote geography, and location hierarchy. Never merge solely on title/company when simultaneous duplicate requisitions are possible.
4. **Inference**: model reposts and relists explicitly. Keep posting instances separate from canonical requisitions, preserve LinkedIn job IDs, and define whether recall counts requisitions or posting instances before analysis.
5. **Inference**: manually review ambiguous many-to-one/one-to-many matches. Publish unmatched and uncertain match counts and run sensitivity bounds that treat uncertain matches once as found and once as missed.

### Temporal and repeated-run design

1. **Inference**: observe the external frame and each search system on at least two distinct UTC days, preferably at fixed UTC times. A job must overlap the frozen availability window for a minimum declared duration or be analyzed in a short-lived-job subgroup.
2. **Inference**: run the unchanged production query matrix repeatedly under controlled client, network class, headers, rate policy, ordering, and delays. Randomize query order within blocks only if the randomization seed is frozen and recorded.
3. **Inference**: persist every request, including empty pages and failures, with exact URL, headers class, UTC timestamp, status, bytes, hash, retry lineage, source-policy grant, parser version, and configuration revision.
4. **Inference**: do not convert a failed request into a miss. Separate `not retrieved after valid completed runs` from `not observable because run/scope failed`.

### Sentinel matrix

**Inference**: the sentinel matrix isolates behavior before the larger recall run. Every cell needs repeated runs on 2+ days; each cell changes one factor only.

| Dimension | Sentinel cells | Required check | Classification |
|---|---|---|---|
| Query breadth | narrow lane phrase; broad role phrase | Top-page overlap, unique cumulative yield, depth transition | **Inference** |
| Syntax | natural text; quotes; `AND`; `OR`; `NOT`; contradiction; nonexistent token | Independently inspect required/excluded terms in title and detail | **Inference** |
| Offset | `0,10,20,25,30,50`, neighboring end offsets, `975,999,1000,1001` only where policy permits | IDs/order, overlap, empty/repeat behavior, status boundary | **Inference** |
| Recency | omitted, `r3600`, `r86400`, `r172800`, `r604800`, `r2592000` | Compare source timestamps to fixed UTC cutoff | **Inference** |
| Geography | location text only; `geoId` only; both; conflicting pair; multiple countries/cities | Independently validate every returned location and known in-scope sentinels | **Inference** |
| Work mode | omitted; `f_WT=1,2,3`; matching natural-language terms | Validate against detail/employer source, including unknown | **Inference** |
| Employment type | omitted; each relevant `f_JT` value; natural-language term | Validate against detail/employer source | **Inference** |
| Language | English/French query crossed with English/French header and UI locale | Recall by posting language and bilingual title family | **Inference** |
| Title/function | title phrase; off-title description mention; `f_F` where observed | Establish whether any filter is strict before using it as a denominator definition | **Inference** |
| Repeatability | immediate pair; spaced within day; same UTC time next day | Jaccard, rank correlation, cumulative new yield, failure rate | **Inference** |
| Interface | guest fragment; unauthenticated interactive; approved independent source | Containment and source-specific misses, without assuming equal universes | **Inference** |

### Three-system dependent capture analysis

1. **Inference**: define capture systems as `A` employer ATS/career sites, `B` an independently operated aggregator/index, and `C` LinkedIn production discovery. Build the complete observed `A/B/C` membership table after canonicalization.
2. **Inference**: direct frame recall against `A` is primary when employer ATS enumeration is credible. Capture-recapture is secondary because systems are dependent: aggregators ingest ATS feeds, employers syndicate selectively, and LinkedIn ranking/availability varies by job type and employer.
3. **Inference**: fit log-linear models to the seven observed capture cells with main effects and defensible pairwise interactions (`AB`, `AC`, `BC`). Compare preregistered candidate models using fit diagnostics and information criteria; report the estimated unobserved `000` cell and total only as a sensitivity analysis.
4. **Inference**: do not use a naive two-list Lincoln-Petersen estimate as the main result. Positive dependence can understate the unseen population; heterogeneous capture probabilities and sparse cells can destabilize estimates.
5. **Inference**: stratify or include covariates for ATS, lane, geography, employer size, posting age, work mode, language, and employment type where cell sizes permit. Collapse strata only under a documented rule; do not publish subgroup estimates with fewer than 30 adjudicated jobs as stable.
6. **Inference**: report model range, bootstrap/profile intervals, observed union, estimated unseen count, and assumptions. If models disagree materially, sparse cells prevent convergence, or source independence is not credible, publish bounds and observed coverage only.

### Uncertainty and missing data

1. **Inference**: report exact numerators/denominators and two-sided 95% Wilson intervals for direct observed proportions. For weighted stratified estimates, use a design-aware interval or bootstrap employers, not individual duplicate postings.
2. **Inference**: classify missingness as source unavailable, blocked/throttled, parser failure, missing required fields, ambiguous eligibility, ambiguous canonical match, or outside temporal overlap. Never fold these categories into "not found."
3. **Inference**: produce best/worst-case recall bounds: unresolved eligible jobs all missed versus all found; uncertain canonical matches unmatched versus matched; transient source failures excluded versus counted as misses where substantively justified.
4. **Inference**: publish per-lane, ATS, geography, age, language, and work-mode distributions. Suppress or clearly flag `n<30` subgroup percentages and do not infer universality from a `>=100` aggregate lane sample.
5. **Inference**: retain raw immutable evidence and hashes under the approved data-retention policy, while minimizing personal data and avoiding unnecessary applicant/member data.

### Success criteria

- **Inference**: each feasible lane has at least 100 adjudicated external-frame jobs, with all subgroup caveats visible.
- **Inference**: collection spans at least two days under one fixed UTC window and one frozen protocol/configuration revision.
- **Inference**: every denominator reconciles through the funnel, and failures/missingness are not relabeled as misses or successes.
- **Inference**: direct frame recall and LinkedIn-conditioned recall are reported separately with uncertainty.
- **Inference**: capture/log-linear estimates are explicitly secondary and include dependence/model sensitivity.
- **Inference**: conclusions remain bounded to sampled employers, ATS strata, geographies, lanes, dates, and interfaces.

## Legal and operational constraints

- **Community/vendor claim**: C5 and related vendors describe litigation, Terms-of-Service risk, throttling, HTTP 999, fingerprinting, and active anti-bot enforcement. This report does not independently verify their legal interpretations and is not legal advice.
- **Official docs**: the official materials inventoried here describe member search and restricted talent products; they do not document the guest endpoint as a supported public Jobs API.
- **Inference**: obtain a current legal/terms/robots review and prefer an authorized API, licensed feed, employer ATS feed, or approved data provider before any expanded study.
- **Inference**: use the project's source-wide request gate, conservative aggregate limits, fixed identity, and circuit breaker. Stop on explicit denial, challenge, `403`, `429`, `999`, or analogous access-control response; do not rotate identities, accounts, proxies, or fingerprints to evade controls.
- **Inference**: external employer and aggregator terms, robots rules, licensing, retention, attribution, and personal-data obligations require separate review. Public accessibility is not authorization.
- **Direct current empirical test**: this pilot observed HTTP 200 and 400 only; it did not establish a safe request rate or absence of anti-bot controls.

## Conclusions

- **Direct current empirical test**: immediate paired runs at `start=0/25/50` were stable at ten IDs each, while a later `start=0` capture changed; determinism is time- and test-bounded.
- **Direct current empirical test**: the interactive capture contained 60 IDs and included all ten IDs from the first guest page for the one tested query.
- **Direct current empirical test**: job-type, work-type, `geoId` omission, and language-header variants yielded identical top tens in this one query; date variants and Boolean-shaped query text yielded different IDs.
- **Direct current empirical test**: `start=975` could be empty and `start>=1000` returned HTTP 400; the broad query still returned cards at `450` but was empty at `490/500`.
- **Inference**: these results characterize a small current retrieval sample. They neither prove ignored filters nor Boolean semantics, and they support a query-specific broad retrievable depth around `<500`, not a universal cap.
- **Inference**: absolute recall remains unidentified until an independently constructed external frame, verified LinkedIn availability, canonical matching, multi-day repeated runs, complete funnel denominators, and explicit uncertainty analysis exist.

No production query change is recommended from this investigation.
