# RadMachine → Org Logbook Importer - Agent Instructions

Check README.org for project context if not in your recent history.

Check TODO.org when identifying tasks or otherwise planning. Update that file when you complete a task by removing the entry, rather than marking done (git will be the history, not that file).

Use multi-line commit messages. First line short summary, subsequent lines give moderate detail in dot points.

Prefer TDD - failing test -> changes -> passing test

* Problem Statement

The logbook already contains curated entries such as:

- Linac monthly QA summaries
- Post-PMI QA summaries
- Service events
- Logged faults
- CT monthly QA entries
- Reflections and follow-up notes

RadMachine contains structured operational data, but the logbook entries are *authored summaries*, not raw exports. A useful tool therefore needs to:

- pull source records from RadMachine,
- infer likely groupings such as “LA7 MQC on 2026-03-30”,
- render an initial draft in Org,
- prompt for manual additions such as notable events,
- preserve source metadata to avoid duplicate imports.

This is an *import-and-review* workflow, not a plain =org-capture= workflow.


* Non-Goals

This repository should *not* aim to:

- auto-write polished final prose with no review,
- replace normal manual note-taking,
- force everything through Org-roam nodes,
- directly mutate the logbook with no confirmation,
- hide source provenance,
- depend on a huge framework for what is basically HTTP + grouping + templating.

* Plan - all the following may have to change

* Proposed Architecture

** Split responsibilities

Use:

- *Python* for RadMachine extraction, normalization, grouping, and rendering
- *Emacs Lisp* for prompting, preview, edit/accept/skip, and insertion into Org

This split keeps the unpleasant parts where they belong:

- HTTP, auth, pagination, grouping logic, and tests in Python
- interactive review and Org insertion in Emacs

Trying to do RadMachine client logic in Elisp would be masochism. Trying to drive interactive Org insertion from Python would be clumsy.

** High-level flow

#+begin_example
Emacs command
  -> prompt for user/date range
  -> call Python CLI
  -> Python fetches RadMachine data
  -> Python normalises records
  -> Python groups records into candidate entries
  -> Python renders draft Org text + emits JSON metadata
  -> Emacs reviews each candidate
      -> accept / edit / skip
  -> Emacs inserts accepted entries into target Org subtree
#+end_example

* Repository Layout

Suggested initial layout:

#+begin_example
radlog/
  __init__.py
  api.py          # RadMachine client
  auth.py         # token / customer configuration
  models.py       # normalized dataclasses / pydantic models
  collect.py      # fetch records for date range/user
  classify.py     # infer work types (MQC, post-PMI, fault, etc.)
  group.py        # collate raw records into candidate entries
  render.py       # Org rendering
  prompts.py      # prompt scaffolding for notable events / follow-up items
  cli.py          # machine-readable CLI for Emacs

elisp/
  radlog.el       # Emacs entrypoint and review UI

tests/
  test_group.py
  test_render.py
  test_classify.py

examples/
  sample_api_payloads/
  sample_output/

README.org
TODO.org
#+end_example

* Data Model

The Python side should define a normalized record model so the rest of the pipeline is not tightly coupled to raw RadMachine payloads.

Suggested normalized record shape:

#+begin_src python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SourceRecord:
    source_type: str          # qa | service_event | fault
    remote_id: str
    created_at: str | None
    updated_at: str | None
    performed_at: str | None
    created_by: str | None
    unit: str | None
    site: str | None
    title: str | None
    status: str | None
    raw: dict[str, Any] = field(default_factory=dict)
#+end_src

Suggested grouped candidate model:

#+begin_src python
@dataclass
class CandidateEntry:
    entry_type: str           # linac_mqc | post_pmi | ct_monthly | fault | service_event | etc.
    group_key: str
    date: str
    title: str
    site: str | None
    unit: str | None
    tags: list[str]
    performed_items: list[dict]
    flagged_items: list[dict]
    notable_prompts: list[str]
    source_ids: list[str]
    rendered_org: str | None = None
#+end_src

* Interchange Format Between Python and Emacs

Use JSON.

Do not make Emacs scrape pretty terminal output. That would be amateur hour.

Example JSON output:

#+begin_src json
[
  {
    "entry_type": "linac_mqc",
    "group_key": "2026-03-30_LA7_linac_mqc",
    "date": "2026-03-30",
    "title": "LA7 MQC",
    "site": "Hayman",
    "unit": "LA7",
    "tags": ["Hayman", "LA7"],
    "performed_items": [
      {
        "category": "Imaging",
        "label": "CatPhan 503 (MFOV+SFOV x CW+CCW)",
        "duration_min": 25
      },
      {
        "category": "Winston Lutz",
        "label": "Gantry+Colli+Couch radiation isocentre, MV-kV alignment",
        "duration_min": 50
      }
    ],
    "flagged_items": [
      {
        "severity": "near_action",
        "category": "Geometry",
        "label": "Light vs Radiation",
        "detail": "X1 1.5 mm off in 6 MV and 1.8 mm off in 10 MV"
      }
    ],
    "notable_prompts": [
      "Review any tolerance/action-level results",
      "Add clinical relevance/context if needed"
    ],
    "source_ids": ["qa:123", "qa:124", "qa:130"],
    "rendered_org": "..."
  }
]
#+end_src

* Rendering Strategy

The rendered Org should be a *draft*, not the final truth.

Example draft for a linac monthly QA candidate:

#+begin_example
**** [2026-03-30 Mon] LA7 MQC :Hayman:LA7:
:PROPERTIES:
:RM_GROUP_KEY: 2026-03-30_LA7_linac_mqc
:RM_SOURCE_IDS: qa:123,qa:124,qa:130
:END:
Performed as rostered duty:
- Imaging :: CatPhan 503 (MFOV+SFOV x CW+CCW)
  - ~25 mins
- Winston Lutz :: Gantry+Colli+Couch radiation isocentre, MV-kV alignment
  - ~50 mins
- Mechanical :: all mechanical tests
- Safety :: Physical, interlocks, EPID drive, kV drive
- MLC :: Leaf speed constancy, DRGS, Picket fence
- EPID :: image quality
- Geometry :: scaling, light vs. radiation, jaw drive accuracy

Notable events:
- Review flagged results:
  - Light vs Radiation near action: X1 1.5 mm off in 6 MV and 1.8 mm off in 10 MV
- Manually enter here
#+end_example

The exact formatting should be customizable in Python, ideally by entry type.

* Entry Type Customisation

Different work types need different renderers.

At minimum, plan for separate renderers or templates for:

- linac monthly QA
- post-PMI QA
- annual QA
- CT monthly QA
- service events
- logged faults
- ABC weekly QA
- on-call / troubleshooting

A simple pattern is:

#+begin_src python
RENDERERS = {
    "linac_mqc": render_linac_mqc,
    "post_pmi": render_post_pmi,
    "ct_monthly": render_ct_monthly,
    "service_event": render_service_event,
    "fault": render_fault,
}
#+end_src

Do not over-generalize too early. The logbook format is heterogeneous and will stay that way.

* Emacs UX

The Emacs side should provide one main interactive command.

Suggested command:

#+begin_example
M-x radlog-import-radmachine
#+end_example

Suggested flow:

1. Prompt for start date.
2. Prompt for end date.
3. Prompt for username or use configured default.
4. Call Python CLI.
5. Receive JSON candidates.
6. For each candidate:
   - open a review buffer,
   - allow free editing,
   - accept / skip / defer.
7. Insert accepted entry into the configured target subtree.

Suggested review commands:

- =C-c C-c= accept and insert
- =C-c C-k= skip
- =C-c C-d= defer / save for later

This is *not* classic =org-capture=. It is a review buffer workflow.

* Duplicate Prevention

This matters. Without it, rerunning an overlapping date range will create duplicate logbook entries.

Each accepted entry should preserve source metadata, at least:

- =RM_GROUP_KEY=
- =RM_SOURCE_IDS=
- maybe =RM_IMPORTED_AT=

Possible future behaviour:

- before insertion, Emacs checks if =RM_GROUP_KEY= already exists in the file
- optionally offer update / replace / skip

* Configuration

Plan for a local config file, for example:

#+begin_example
config.toml
#+end_example

Suggested fields:

#+begin_src toml
[radmachine]
base_url = "https://radmachine.radformation.com"
customer_id = "tcc"
username = "gillmanas"
token_env = "RADMACHINE_TOKEN"

[logbook]
default_file = "~/org/teap-logbook.org"
default_heading = "TCC Logbook"
timezone = "Australia/Brisbane"

[grouping]
merge_same_day_same_unit = true

[render]
include_durations = true
include_flagged_items = true
#+end_src

Secrets should come from environment variables, not from committed files.

* RadMachine Notes

Publicly available RadMachine examples indicate:

- token-based auth via =RadAuthorization: Token <token>=
- base URL shape like =https://radmachine.radformation.com/{customer_id}/api/...=
- paginated responses with =results=
- Django/DRF-style filtering patterns in example code

However, public examples do *not* appear to fully document all endpoints for service events and faults. Expect endpoint discovery or instance-specific inspection to be required.

Therefore the implementation should:

- isolate endpoint definitions in one place,
- be tolerant of partial knowledge,
- support stub/example payloads for development,
- avoid baking undocumented assumptions throughout the codebase.

* Confirmed API Map

This section summarizes what has been confirmed from the public examples and the
live TCC instance. Treat this as the current working map of the API.

** Auth and base URL

- Header: =RadAuthorization: Token <token>=
- Base API root: =https://radmachine.radformation.com/{customer_id}/api/=
- Token should come from an environment variable, not committed config
- Responses observed are JSON and DRF-style

** API roots observed on the live instance

#+begin_src json
{
  "/api/": [
    "auth",
    "attachments",
    "backups",
    "contenttypes",
    "faults",
    "parts",
    "qa",
    "reports",
    "schema",
    "servicelog",
    "units"
  ],
  "/api/qa/": [
    "autoreviewrules",
    "autoreviewrulesets",
    "categories",
    "frequencies",
    "references",
    "reviewstatus",
    "sublists",
    "testinstances",
    "testlistcycles",
    "testlistcyclememberships",
    "testlistinstances",
    "testlists",
    "testlists-details",
    "testlistmemberships",
    "tests",
    "tolerances",
    "unittestcollections",
    "unittestinfos"
  ],
  "/api/units/": [
    "availabletimeedits",
    "availabletimes",
    "modalities",
    "rooms",
    "sites",
    "storages",
    "unitclasses",
    "units",
    "unittypes",
    "vendors"
  ]
}
#+end_src

** Object model that matters for QA imports

#+begin_src text
testlists
  = template / definition of a test list

unittestcollections
  = assignment of a test list to a unit
  = useful human name for the assigned QA activity
  = has unit, due_date, last_instance, frequency

testlistinstances
  = one performed QA session
  = has work_started/work_completed, comments, flagged, embedded test_instances
  = links to unit_test_collection and test_list

testinstances
  = one individual result row within a performed session
  = has value/pass_fail/skipped/work_completed plus links to unit_test_info and test_list_instance
#+end_src

For authored logbook imports, the most promising primary source is
=qa/testlistinstances/=, with =unittestcollections= and =units/units= used as
lookup/context.

** Useful confirmed filters

These are based on the public example scripts and live probing.

#+begin_src text
GET /api/qa/testinstances/
  created_by__username=<username>
  unit_test_info__unit__name=<unit name>
  unit_test_info__test__name=<test name>
  skipped=False
  ordering=-work_completed
  limit=<n>
  offset=<n>

GET /api/qa/testlistinstances/
  unit_test_collection__unit__name=<unit name>
  unit_test_collection__test_list__name=<test list name>
  ordering=-work_completed
  limit=<n>
  offset=<n>

GET /api/qa/unittestcollections/
  unit__name=<unit name>
  test_list__name=<test list name>
  limit=<n>
  offset=<n>
#+end_src

It is reasonable to expect other Django/DRF relation filters to work, but treat
that as inference until verified on the live instance.

** Response shapes worth remembering

Paginated endpoints use the DRF envelope:

#+begin_src json
{
  "count": 13308,
  "next": "https://...offset=10",
  "previous": null,
  "results": [ ... ]
}
#+end_src

Representative =testlistinstance= fields:

#+begin_src text
url
comments[]
test_instances[]
site_url
report_url
work_started
work_completed
due_date
flagged
reviewed
unit_test_collection
test_list
created_by
modified_by
#+end_src

Representative =unittestcollection= fields:

#+begin_src text
url
name
unit
frequency
due_date
last_instance
tests_object
next_test_list
#+end_src

Representative =units/units= fields:

#+begin_src text
pk
url
name              # e.g. "LA7 - Hayman"
site
type
active
is_serviceable
modalities
attributes
#+end_src

** Concrete known mapping

Known real example:

- Site URL: =/tcc/qa/session/details/13162/=
- API record: =/tcc/api/qa/testlistinstances/13162/=
- Linked collection: =/tcc/api/qa/unittestcollections/206/=
- Collection name: =Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV=
- Linked unit: =/tcc/api/units/units/2/=
- Unit name: =LA7 - Hayman=

This indicates that a report title such as:

#+begin_example
LA7 - Hayman - Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV - 06 Mar 2026 10:10 AEST
#+end_example

is effectively composed from:

- unit name from =units/units/<id>=
- assignment name from =unittestcollections/<id>=
- performed timestamp from =testlistinstances.work_completed=

** Grouping implication

Do not assume one authored logbook entry equals one RadMachine
=testlistinstance=. A monthly QA summary is likely composed of multiple sibling
=testlistinstances= on the same date/unit whose collection names share a common
prefix such as =Linac Monthly ::=.

* Development Approach

Recommended order of attack:

1. Build normalized models.
2. Implement client code for one known endpoint first.
3. Save raw payload fixtures.
4. Write grouping logic against fixtures.
5. Write renderer tests.
6. Build CLI JSON output.
7. Add Emacs review/insertion command.
8. Add duplicate detection.
9. Add more endpoint support.

If this is done in the opposite order, the result will likely be a bag of stringly-typed regrets.

* Testing Strategy

Testing should focus on three things:

** 1. Classification
Given realistic payloads, can the system infer:

- LA7 MQC
- post-PMI QA
- CT monthly QA
- service event
- fault

** 2. Grouping
Given multiple source records on the same date/unit, can the system correctly:

- merge related QA items,
- avoid merging unrelated work,
- preserve source provenance,
- surface flagged items.

** 3. Rendering
Given a =CandidateEntry=, does the rendered Org:

- match expected heading format,
- include required performed items,
- include metadata properties,
- include prompt scaffolding for manual additions.

Golden-file tests for Org output are appropriate here.

* Example User Story

#+begin_quote
From Emacs, the user runs =radlog-import-radmachine=. They enter a date range. The tool pulls RadMachine entries for that user. It notices a set of records corresponding to “LA7 MQC” on 2026-03-30 and drafts a grouped Org entry. It also notices CT monthly QA on another date and drafts that separately. For each draft, the user can edit, accept, or skip. Accepted entries are inserted into the logbook under the correct subtree.
#+end_quote

That is the core product. Not AI prose generation. Not note-taking theology. Just a competent import-review-insert workflow.

* Future Extensions

Possible future additions:

- search existing Org for related entries and suggest backlinks
- richer prompt scaffolding for notable events
- auto-detect tolerance/action-level tests and prompt explicitly
- support update/re-render of previously imported entries
- attachment/link support for service reports
- optional SQLite cache for sync state and payload history
- fuzzy destination routing to different logbook subtrees
- org-id creation if missing

These are fine later. Do not start with them.

* Suggested First Milestone

A reasonable v0 milestone is:

- Python CLI accepts start/end/user
- returns mocked or real grouped JSON
- Emacs command reviews candidates one-by-one
- accepted drafts insert into an Org file
- imported entries carry =RM_GROUP_KEY= and =RM_SOURCE_IDS=

If that works, the architecture is sound. If it does not, the rest was fantasy.
