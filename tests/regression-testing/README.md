# Regression testing

This suite automates the Archivematica release regression checklist kept in
the [testing-checklists](https://github.com/archivematica/testing-checklists)
repository. Every checklist item is a pytest-bdd scenario that drives a
freshly installed Archivematica through its APIs and, where the item is about
the user interface, through a Playwright browser. Each scenario leaves an
evidence bundle behind so an analyst can judge the result without re-running
it.

## Software requirements

- Podman and podman-compose
- Python 3 (for Ansible) and [uv](https://docs.astral.sh/uv/) (for the suite)
- 7-Zip (`p7zip-full`) to extract the stored AIPs
- curl and jq

## Layout

```
compose.yaml                        Archivematica and AtoM systemd containers
                                    (tests/common/Dockerfile)
archivematica.yml, atom.yml         Ansible playbooks, copied from the DIP upload test
archivematica-vars.yml              variables of the Archivematica playbook: credentials, XML
                                    validation, FITS disabled, emails written to files, DIP
                                    upload settings
vars-qa.yml                         variables of the qa release line: refs and MySQL version
vars-1.18.yml                       variables of the 1.18 release line: refs and MySQL version
atom-vars.yml                       variables of the AtoM playbook
requirements-qa.yml                 the Ansible roles of the qa release line
requirements-1.18.yml               the Ansible roles of the 1.18 release line
requirements.txt                    the Python packages of the Podman test setup
suite/
  conftest.py                       pytest and pytest-bdd glue: fixtures, markers, checklist
                                    coverage and the evidence hooks
  hack-stack.env                    settings for the Archivematica Docker Compose development stack
  checklist/                        vendored copy of regression-testing-checklist.csv
  features/                         one feature file per checklist area, one scenario per item
  steps/
    pipeline_steps.py               steps that drive the pipeline through its APIs and check jobs
                                    and packages
    mets_steps.py                   steps that check the AIP and its METS file against the sample
                                    transfer
    normalization_steps.py          steps that check derivatives, events and the DIP after
                                    normalization
    format_steps.py                 steps for identification, extraction and validation
    failure_steps.py                steps for failed transfers and the failure email
    fpr_steps.py                    steps that change the Format Policy Registry through
                                    Preservation planning and put it back
    ui_steps.py                     steps that drive the dashboard through a browser, including
                                    the decisions taken from the Ingest tab
    transfer_tab_steps.py           steps for the Transfer tab: the file browser, custom
                                    processing configurations, disk image metadata, removals
    metadata_steps.py               steps for the rights and descriptive metadata forms of a SIP
    manual_normalization_steps.py   steps that insert manually normalized files and fill in the
                                    event detail form
    admin_steps.py                  steps for Administration: processing configurations, storage,
                                    languages, users and failure reports
    storage_steps.py                steps for the AIP storage page, re-ingest, deletion requests,
                                    DIP deletion and encrypted or replicated locations
    atom_steps.py                   steps for DIP uploads to AtoM, checked in AtoM's database
    contentdm_steps.py              steps for the CONTENTdm DIP upload, which only restructures
                                    the DIP
    mets_validation_steps.py        steps that validate the AIP METS against its schemas and the
                                    Archivematica rules of metsrw
  rt/
    settings.py                     runtime configuration, read from RT_* environment variables
    checklist.py                    the checklist, loaded from the vendored CSV
    scenario.py                     per-scenario state shared between the Given and When steps
    known_failures.py               the boxes expected to fail, from suite/known-failures.toml
    evidence.py                     the evidence bundle written for every scenario
    report.py                       merges the bundles of a run into the checklist markdown, a
                                    summary and an index page
    pipeline/am_api.py              client for the dashboard API of the pipeline
    pipeline/ss_api.py              client for the Storage Service API
    pipeline/web.py                 forms and pages of the dashboard and the Storage Service
                                    outside their APIs, through a logged-in session
    pipeline/fpr.py                 the Format Policy Registry through the dashboard pages
    pipeline/cookies.py             the cookie jar of the form logins
    pipeline/container.py           files and logs of the pipeline container through Compose
    pipeline/processing_config.py   processing configurations rendered per scenario from one of the
                                    pipeline's own files
    pipeline/decisions.py           decision points of the workflow and the targets of their choices
                                    (generated)
    pipeline/packages.py            fetches stored packages from the Storage Service into a bundle
    assertions/aip.py               checks on the structure of a stored AIP
    assertions/mets.py              read-only access to an AIP METS file for the assertions
    assertions/validation.py        validation of an AIP METS against its schemas, offline, and
                                    against the Archivematica schematron that metsrw ships
    schemas/                        local copies of the PREMIS 3, xlink, xml and Dublin Core
                                    schemas
  tests/test_scenarios.py           collects every feature file as a test module
  tools/extract_decisions.py        regenerates rt/pipeline/decisions.py from an Archivematica
                                    workflow.json
```

## Installing Archivematica

Follow the same steps as the [DIP upload test](../dip-upload/README.md) with
this directory: copy your SSH public key to `ssh_pub_key`, choose the image
with `ARCHIVEMATICA_DOCKER_IMAGE_NAME` and `ARCHIVEMATICA_DOCKER_IMAGE_TAG`,
start the Compose services and run `archivematica.yml`. Install AtoM with
`atom.yml` only for the shards that need it (the `atom` shard).

The installation follows a release line (see Release lines below): install
the roles of the line and pass the line to the playbook as `release`, which
checks that its variables file exists:

```shell
../common/prepare-ansible-roles requirements-qa.yml
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, archivematica.yml \
    -u ubuntu \
    -e "release=qa" \
    -v
```

The containers keep the MySQL release they installed first, 8.4 for `qa` and
8.0 for `1.18`, so recreate them with `podman-compose down` and
`podman-compose up --detach` before installing another line.

The `archivematica_src_am_version` and `archivematica_src_ss_version`
variables override the refs of the line, for a tag or a SHA:

```shell
../common/prepare-ansible-roles requirements-1.18.yml
ansible-playbook -i localhost, archivematica.yml \
    -u ubuntu \
    -e "release=1.18" \
    -e "archivematica_src_am_version=v1.18.0" \
    -e "archivematica_src_ss_version=v0.24.0" \
    -v
```

`archivematica-vars.yml` sends the emails of the pipeline, such as the fail and
normalization reports, to files under `/var/archivematica/sharedDirectory/mail`
in the container, since it has no mail server. The suite reads them from
there (`RT_MAIL_DIR`); when that variable is empty, as against the development
stack, it looks for the messages in the output of the services instead.

Add the `ubuntu` user to the `archivematica` group and check the APIs:

```shell
podman-compose exec --user root archivematica usermod -a -G archivematica ubuntu
../common/check-archivematica-apis
```

## Release lines

A release line is a pair of files next to the playbooks:
`requirements-<release>.yml` pins the branch of the archivematica-src role,
and `vars-<release>.yml` the Archivematica and Storage Service refs and the
MySQL version. The playbook loads the pair named by `release`, and the
workflow discovers the lines from the requirements files, so a line is
added, not configured. Two lines exist today: `1.18`, the stable branches of
Archivematica 1.18 and Storage Service 0.24 with the `stable/1.18.x` role,
and `qa`, which follows `qa/1.x`, `qa/0.x` and the `qa/1.x` role and is
therefore a moving target: it is whatever the next release will be.

The suite never tests by line name. It reads the version the pipeline
reports in `X-Archivematica-Version` and the markup it serves: the browser
steps choose the dashboard implementation from the version
(`rt/pipeline/dashboard_ui.py`, Vue from 1.19 on, AngularJS before), the FPR
client and the Storage Service steps read whichever markup they get, the
decision table (`rt/pipeline/decisions.py`) merges the workflows of every
line, and a known failure lists the versions it applies to as prefixes in
its `releases`.

### Adding a line

Create `requirements-<release>.yml` and `vars-<release>.yml`; the next push
runs the line. Then, only as needed: regenerate `rt/pipeline/decisions.py`
with `tools/extract_decisions.py` from the `workflow.json` of every line when
the decisions of the new line differ, add `releases` entries to
`suite/known-failures.toml` for the boxes that fail only on it, and write
another implementation behind the interface of `dashboard_ui.py` only if its
pages differ from both the Vue and the AngularJS dashboards.

### When the qa line is released

When `qa/1.x` is cut as `stable/1.19.x`, the new line is the pair
`requirements-1.19.yml` and `vars-1.19.yml`: the role at its `stable/1.19.x`
branch once it exists (until then the `qa/1.x` role installs 1.19 as well),
and the stable branches of Archivematica and the Storage Service with the
MySQL version the release supports. `qa` keeps following the development
branches and becomes the 1.20 line without any edit. The suite needs no
change either: stable 1.19 gets the Vue implementation like `qa`, its
decisions are already in the merged table, since the workflows are equal at
the cut, and the known failures marked `1.19` apply to it for as long as the
defect ships in it, point releases included. They stop applying to `qa` the
moment it reports 1.20.0; until then both lines report 1.19.0 and are
treated alike, which is right because they are the same code.

Two things follow. A box that still fails on `qa` once it reports 1.20.0
turns red instead of known: extend the entry with `1.20`, or better fix the
defect upstream and drop the entry when the suite warns that it passes. And
every automatic run grows by one line: with three lines a push, a pull
request or the schedule is fifty-four jobs, while a manual run can name one
line with the `release` input.

### Retiring a line

Delete its two files. The implementation and the known failure entries that
only that line used become unused but harmless, and can go whenever
convenient.

## Running the suite

Create the suite environment:

```shell
cd suite
uv sync --locked
```

A shard is a group of scenarios that share one deployment and one set of
companions, and runs as one job per release line and operating system with
its own evidence artifact. The split follows two rules: scenarios that need
nothing beyond the pipeline share the common shards, which keeps those cheap,
and anything that needs a different install (AtoM, an indexless pipeline) or
a long runtime (the performance items) gets a shard of its own. The workflow's
matrix job defines the shards and the companions each one installs:

- `transfer`: the pipeline-driven scenarios, which only need the dashboard and
  Storage Service APIs (areas 1 to 6, 8, 11, 17 and 20 today, plus the
  CONTENTdm upload of 12.4, which only restructures the DIP)
- `normalization`: the normalization scenarios, which also fetch the DIP from
  the Storage Service and the task output from the dashboard (area 9)
- `identification`: the scenarios that change the Format Policy Registry through
  Preservation planning, with a browser, and put it back afterwards (5.3, 5.4
  and area 14)
- `dashboard`: the scenarios that drive the dashboard through a browser with
  Playwright: the Transfer tab, metadata forms, manual normalization,
  Administration, users and failure reports (areas 1, 9, 10, 11, 15, 16 and 17)
- `storage`: the archival storage scenarios, which use the AIP storage page of
  the dashboard and the Storage Service's own pages, with a browser for both
  (areas 13 and 19); the encrypted and replicated location scenarios create a
  GPG key, a space and locations in the Storage Service, named after their
  checklist item, and reuse them on later runs
- `atom`: the DIP upload scenarios, which need the AtoM companion the workflow
  installs next to the pipeline (12.1, 12.3 and 13.1); they upload to the
  description the AtoM sample import creates (`RT_ATOM_TARGET_SLUG`) and
  check the result in AtoM's database through its container

The `@shard-<name>` tag of a scenario places it in a shard and its `@needs-`
tags declare the companions it requires. A new shard, such as an AtoM shard
for the DIP upload items, is an entry in the workflow matrix naming the
companions to install. The full checklist fits in six shards; every release
line times three operating systems times six shards is, with the two lines of
today, thirty-six jobs of under an hour each, about twice the nightly AMAUAT
matrix.

Run one shard or every shard:

```shell
uv run --locked pytest --shard transfer
uv run --locked pytest
```

Scenarios tagged `@needs-browser` use Playwright. Install a browser once:

```shell
uv run --locked playwright install --with-deps firefox
uv run --locked pytest --shard dashboard --browser firefox
```

The suite reads its settings from `RT_*` environment variables; the defaults
match the Podman layout of this directory. `rt/settings.py` lists them.

To run against the Docker Compose development stack of the Archivematica
repository instead, load `suite/hack-stack.env` first:

```shell
set -a; source hack-stack.env; set +a
uv run --locked pytest --shard transfer
```

The METS validation scenarios (area 20) need no network: libxml2 2.14, which
lxml 6 bundles, cannot fetch the schemas a METS file names. They validate
against the METS schema that metsrw bundles and the copies in
`suite/rt/schemas/`: PREMIS 3, xlink and xml.xsd as Archivematica bundles them
under `MCPClient/assets`, and the Dublin Core schemas of 2008-02-11 from
dublincore.org. The Dublin Core schemas declare the elements but not the
`dcterms:dublincore` container Archivematica wraps them in, so the content of
each element is checked and the container's own content is not. The hooks in
`.pre-commit-config.yaml` leave those copies as published. 20.2 runs the Archivematica schematron that metsrw ships; two of its
rules predate the METS Archivematica writes (its list of PREMIS event types,
and its reading of a DMDID that names several dmdSecs), so their hits become
warnings instead of failures.

## Evidence

Every scenario writes `evidence/<platform>/<item id>/`:

- `result.json`: the outcome of each criterion, the units and packages the
  scenario created, timestamps, notes and warnings about jobs that failed
  without failing the scenario
- `processing-config/`: the processing configuration the scenario used
- `jobs/`: the jobs of every unit and, for the jobs that failed, each task
  with its standard streams as the dashboard shows them
- `aip/`: the stored AIP (when smaller than `RT_AIP_SIZE_CAP`), its METS and
  pointer file; the extracted copy is removed at the end of the scenario unless
  `RT_KEEP_EXTRACTED_AIP=1`
- `logs/`: the journal of the scenario's time window, and the Compose output
  when the services wrote any
- `trace.zip` and `screenshots/`: the Playwright trace (open it at
  https://trace.playwright.dev/ or with `playwright show-trace`) and a
  screenshot per step, for browser scenarios; `trace-storage-service.zip` is
  the trace of the Storage Service pages, which run in a browser context of
  their own
- `downloads/`: the files the scenario downloaded through the browser or the
  Storage Service, such as the AIP, its METS or its pointer file
- `aip-before-reingest/`: the METS of an AIP as it was before a re-ingest
  scenario replaced it
- `manual-normalization/`: the files inserted by hand for the manual
  normalization scenarios

Render the checklist, a summary and an index page from the bundles:

```shell
uv run --locked python -m rt.report --evidence-dir evidence --out report
```

`report/checklist-<platform>.md` follows the layout of the release testing
issue template, with the boxes ticked by the run, so it can be pasted into the
release testing issue. `report/summary.md` lists the items that need a look:
failed, pending, not run, and passed with warnings; known failures get their
own section.

`suite/known-failures.toml` lists the boxes expected to fail until a known
problem is fixed, each with its reason and, optionally, the platforms it
applies to. Such a box is reported as a known failure and the scenario counts
as an expected failure, so the job stays green while nothing new fails. When
a listed box passes, the item gets a warning asking for the entry to be
removed. Next to the platforms, an entry may also list the releases it applies
to, as Archivematica version prefixes such as `1.19`.

## Checklist coverage

The CSV under `suite/checklist/` is the source of truth. pytest reports the
items that have no scenario yet; `--strict-coverage` turns that into an
error. Scenario tags map to the checklist: `@item-1.2` names the item,
`@shard-<name>` selects the workflow shard and `@needs-<companion>` the
companions the scenario requires. The `Then` steps of a scenario correspond
one-to-one, in order, to the checklist bullets of the item. A step calls
`evidence.pending(reason)` when a bullet cannot be decided yet, which leaves
the box unticked with the reason in the report, and `evidence.fail(reason)`
when a bullet fails but the later bullets can still be judged: the scenario
goes on and fails at the end. A step that changes global pipeline state, such
as the Format Policy Registry, registers the undo action with the `restore`
fixture, which runs the actions in reverse order when the scenario ends,
whatever its outcome.

## Workflow

`.github/workflows/regression-testing.yml` runs the shards on a matrix of
release lines and operating systems (Ubuntu 22.04, Ubuntu 24.04 and Rocky
Linux 9 by default), uploads an `evidence-<release>-<os>-<shard>` artifact for
every job whether it passed or not, and renders the checklist report in a
final job. The release lines are discovered from the `requirements-<release>.yml`
files of the test, and the matrix job fails when a line lacks its
`vars-<release>.yml`. Pushes, pull requests and the weekly schedule run every
line. A manual run names one with the `release` input, or `all`; its
`am_version` and `ss_version` inputs override the refs of the line when they
are not empty. The platform label of a job, `RT_OS_LABEL`, is
`<os>-<release>`, such as `noble-qa` or `rocky9-1.18`, so the report renders a
checklist per operating system and line. The platforms of a known failure
match any part of the label, so `noble` covers both lines.
