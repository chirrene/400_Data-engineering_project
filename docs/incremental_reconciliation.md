# Incremental collection reconciliation — November 22, 2026

No original export was replaced and PostgreSQL was not accessed. This investigation
made 31 targeted API requests, preserving all 730 original page checkpoints, the
original collection summary, and original collected records. New responses are saved
in `data/incremental/nasa_library/reconciliation/pages/`.

## Findings

### Mars: one ID omitted by year filtering, already in the original dataset

The only original Mars relationship absent from the incremental collection is
`PIA17820` (Ascraeus Mons). The original image and its Mars relationship both exist.
Its live API timestamp is `2013-12-31T16:30:52Z`.

Direct requests with `q=Mars`, `media_type=image`, and `nasa_id=PIA17820` produced:

| Year filter | Hits | Items |
|---|---:|---:|
| None | 1 | 1 |
| 2013–2013 | 0 | 0 |
| 2014–2014 | 0 | 0 |
| 2013–2014 | 1 | 1 |

The cached 1994–2032 parent reports 26,781 hits, but its 1994–2013 and
2014–2032 children report 12,625 + 14,155 = 26,780. The evidence points to a
reproducible year-end filtering inconsistency. It does not establish NASA's internal
filter implementation. The lost timestamp occurs on the last day of the 2013 child.

The additive recovery file restores this ID to Mars's collected set, bringing it to
26,903 unique IDs. A future merge would retain the original record's metadata and
relationship. No original data was missing or lost.

### Earth 1994–2003: distinct assets share one NASA ID

Cached page 16 contains two occurrences of `Air Force Space Command`:

| Zero-based item position | Asset path | Title |
|---|---|---|
| 59 | `image/03pd0069/collection.json` | `030112-F-6844O-002` |
| 74 | `image/03pd0068/collection.json` | `030112-F-6844O-003` |

Both have timestamp `2003-01-12T00:00:00Z`. Refreshing page 16 reproduced these
results with the same ID set. These are different assets with an ID collision, not
proof that another unique NASA ID was missed. All 5,643 result items were fetched;
they represent 5,642 unique NASA IDs.

Neither the colliding ID nor its Earth relationship exists in the original exports.
The required `(source_api, source_id)` key can retain only one of the two assets as
an image row. Existing first-occurrence selection remains in effect. Both raw assets
are preserved in the original and recovery page checkpoints. No substitute IDs were
invented. Retaining both as separate image rows would require a separately approved
identity-policy change; this reconciliation does not change that policy.

### Earth 2024–2032: reproducible API response inconsistency

Refreshing only page 10 again returned 99 items and `total_hits=4166`; the other
cached pages report 4,167. The refreshed page had no new or removed IDs.
Year-specific probes gave:

| Year | API hits | IDs already cached for that year |
|---|---:|---:|
| 2024 | 960 | 960 |
| 2025 | 1,106 | 1,106 |
| 2026 | 2,101 | 2,100 |
| 2027 | 0 | 0 |

Only the affected 2026 subrange was paginated: 22 pages total, reusing the first-page
probe and making 21 additional requests. Its page 4 returned 99 items and reduced its
total to 2,100, while the other pages reported 2,101. All returned IDs were already in
the original incremental collection. The union contains exactly 2,100 unique IDs.
The short result follows the underlying search results into the narrower range.

The API still advertises one result that it does not return in these responses.
The unavailable record's identity and the internal reason (for example response
filtering or stale index metadata) cannot be established from the available evidence.
It is not justified to claim that the result was recovered or that it is already in
the original dataset. Every existing original Earth relationship *is* present among
the 41,211 collected Earth IDs, so no previously collected Earth ID is lost.

## Outputs and preservation

The unchanged original `collection_summary.json` remains `incomplete` with its
historical counts. New outputs are separate:

- `reconciliation_summary.json`: machine-readable audit, duplicate asset details,
  page anomalies, original-data comparison, recovery query groups, hashes, and limitations.
- `reconciliation/reconciled_records.jsonl`: validated union of original incremental
  records and targeted responses. Mars: 26,903 IDs; Earth: 41,211 IDs.
- `reconciliation/pages/*.json`: all 31 targeted response checkpoints, with request
  parameters, complete payloads, and payload checksums.

The proposed union with the original exports has 73,937 images and 80,809 topic
relationships: 42,412 added images and 48,119 added relationships. This is an offline
preview, not a modification of the exports. The seven other topic counts remain
unchanged. All original 31,525 images and 32,690 relationships are preserved.

Original SHA-256 values remain:

```text
clean_images.jsonl  ba52a88cd32fae4aacc5280abc527fcae12357e94df15dab9c51031a4affb22f
image_topics.jsonl  6fd9789911c99168c7ba6b73e86ef1af82925010bb573c7ed5da5defa877b83c
```

## Next commands: offline review

```sh
cd /Users/zhuxumo/Desktop/400_Data-engineering_project
/opt/anaconda3/bin/python -m src.processing.reconcile_collection audit
cat data/incremental/nasa_library/reconciliation_summary.json
```

`audit` is offline. To rebuild the recovery union/report from saved evidence without
any new API requests:

```sh
/opt/anaconda3/bin/python -m src.processing.reconcile_collection build
```

Do not restart `collect` to resolve these discrepancies; it will reuse the historical
responses. Never delete the successful original checkpoints. Targeted checks can be
repeated when useful, always into new checkpoint files, for example:

```sh
/opt/anaconda3/bin/python -m src.processing.reconcile_collection fetch --topic Earth --start-year 2026 --end-year 2026 --page 4
```

A fetch does not automatically alter the recovery union. Run `build` afterward to
incorporate it. New evidence invalidates any previously prepared partial candidate.

## Explicit partial-coverage option, not approved or run during this investigation

Full asset coverage cannot be certified because of the Earth ID collision and
unavailable advertised result. Status therefore remains `incomplete`, even though the
Mars ID difference is reconciled. `prepare`, `verify`, and `merge` all refuse this
run by default. The explicit option accepts the limitations above; it does not
change the API totals or relabel the run as complete.

If you choose to accept these documented limitations, prepare and verify candidates:

```sh
/opt/anaconda3/bin/python -m src.processing.incremental_collection prepare --approve-partial-coverage
/opt/anaconda3/bin/python -m src.processing.incremental_collection verify --approve-partial-coverage
cat data/incremental/nasa_library/validation_summary.json
```

These two commands do not replace original exports. Their report retains
`collection_status=incomplete`, `partial_coverage_approved=true`, and all coverage
limitations. It binds the exact recovery report, response checkpoints, recovered
records, and original export hashes. An altered report, evidence file, or original
export requires rebuilding/reviewing/preparing again.

Only a later, explicit decision to publish should use:

```sh
/opt/anaconda3/bin/python -m src.processing.incremental_collection merge --approve-partial-coverage
```

This command was **not run**. Approval is required again at merge even if preparation
was approved. Existing backup, validation, journal, and rollback protections apply.
PostgreSQL remains a separate manual operation, outside this investigation.

## Tests

```sh
/opt/anaconda3/bin/python -m unittest discover -s tests -p '*collection.py' -v
```

36 offline tests cover the original workflow plus audit evidence, distinct assets
sharing one ID, additive recovery, unchanged checkpoints, targeted-page fetching,
partial approval at every stage, incomplete labeling, stale evidence/report rejection,
checksums, and exact preservation. Merge tests operate only on temporary fixtures.
