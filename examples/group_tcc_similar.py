"""Example grouping rules module for TCC-like logbook imports.

Point `[grouping].rules` at `group_tcc_similar:RULES` with `./examples` in
`[extensions].paths`, then customize this file or copy it into a personal
radlog extensions directory.
"""

from __future__ import annotations

from dataclasses import dataclass

from radlog.models import CandidateEntry, LinkRef, PerformedItem, SourceRecord
from radlog.site_rules import SiteRules


@dataclass(slots=True)
class TccContext:
    monthly_bucket_keys: set[tuple[str, str]]


class TccSimilarRules(SiteRules):
    """TCC-like authored-logbook grouping rules."""

    def prepare(self, records: list[SourceRecord]) -> TccContext:
        return TccContext(
            monthly_bucket_keys={
                (record.performed_at[:10], record.unit)
                for record in records
                if record.performed_at
                and record.unit
                and self._infer_entry_type(record) == "linac_mqc"
            }
        )

    def bucket_key(self, record: SourceRecord, context: TccContext) -> tuple[str, str, str]:
        if not record.performed_at or not record.unit:
            raise ValueError("Cannot bucket a record without performed_at and unit")
        date = record.performed_at[:10]
        entry_type = self._infer_entry_type(record)
        return (
            date,
            self._bucket_unit(record, entry_type),
            self._group_label(record, entry_type, context),
        )

    def build_candidate(
        self,
        bucket_key: tuple[str, str, str],
        records: list[SourceRecord],
        context: TccContext,
    ) -> CandidateEntry:
        date, unit, label = bucket_key
        first = records[0]
        entry_type = self._resolve_entry_type(self._infer_entry_type(first), records)
        site = first.site

        if entry_type == "linac_mqc":
            title = f"{unit} MQC"
            tags = [tag for tag in (site, unit) if tag]
            group_label = label
        elif entry_type == "post_pmi":
            title = f"{unit} post-PMI"
            tags = [tag for tag in (site, unit) if tag]
            group_label = "post_pmi"
        elif entry_type == "abc_weekly":
            title = "ABC Weekly"
            tags = ["ABCWeekly"]
            group_label = "abc_weekly"
            unit = "ABC"
        elif entry_type == "abc_ad_hoc":
            title = "ABC Ad hoc QA"
            tags = [_compact_tag(first.unit)]
            group_label = "abc_ad_hoc"
            unit = "ABC"
        elif entry_type == "linac_ad_hoc":
            title = f"{unit} Ad hoc QA"
            tags = _split_linac_service_tags(first.unit)
            group_label = "linac_ad_hoc"
        elif entry_type == "ct_ad_hoc":
            title = f"{unit} Ad hoc QA"
            tags = []
            group_label = "ct_ad_hoc"
        elif entry_type == "ct_monthly":
            title = first.title or f"{unit} Monthly QA"
            tags = []
            group_label = "ct_monthly"
        elif entry_type == "ct_quarterly":
            title = first.title or f"{unit} Quarterly QA"
            tags = []
            group_label = "ct_quarterly"
        elif entry_type == "arpansa_calibration":
            title = first.title or "ARPANSA Calibration"
            tags = _equipment_tags(first.unit)
            group_label = title
        elif entry_type == "monthly_dosimetry":
            title = "Monthly dosimetry"
            tags = []
            group_label = "monthly_dosimetry"
            unit = "Monthly dosimetry"
        elif entry_type == "ad_hoc_qa":
            title = f"{unit} Ad hoc QA"
            tags = [tag for tag in (site, unit, "AdHocQA") if tag]
            group_label = "ad_hoc_qa"
        else:
            title = first.title or f"{unit} QA"
            tags = [tag for tag in (site, unit) if tag]
            group_label = label

        metadata = _record_urls_metadata(records, entry_type)
        destination_id = _destination_id(entry_type, records)
        if destination_id:
            metadata["destination_id"] = destination_id
        if entry_type in {"abc_ad_hoc", "linac_ad_hoc", "ct_ad_hoc", "ad_hoc_qa"}:
            performed_items = _service_event_performed_items(records)
            prompts = _service_event_detail_prompts(records)
            metadata.update(_service_event_metadata(records))
        elif entry_type == "monthly_dosimetry":
            performed_items = _monthly_dosimetry_items(records)
            prompts = list(dict.fromkeys(self._notable_prompts(records, entry_type)))
            metadata["suppress_links_block"] = True
        elif entry_type == "arpansa_calibration":
            performed_items = [_arpansa_calibration_item(first)]
            prompts = []
        else:
            performed_items = self._aggregate_performed_items(
                entry_type,
                [self._map_performed_item(record, entry_type) for record in records],
            )
            prompts = self._additional_notable_prompts(entry_type, records) + self._notable_prompts(
                records,
                entry_type,
            )

        return CandidateEntry(
            entry_type=entry_type,
            group_key=f"{date}_{unit}_{group_label}",
            date=date,
            title=title,
            site=site,
            unit=unit,
            tags=tags,
            performed_items=performed_items,
            notable_prompts=prompts,
            source_ids=[f"{_source_prefix(record)}:{record.remote_id}" for record in records],
            metadata=metadata,
        )

    def _infer_entry_type(self, record: SourceRecord) -> str:
        title = (record.title or "").strip()
        if title in {"ARPANSA Calibration", "ARPANSA Electrometer Calibration"}:
            return "arpansa_calibration"
        if title in {
            "Sr-90 Constancy",
            "Electrometer Constancy",
            "Thermometer Constancy",
            "Barometer Constancy",
        }:
            return "monthly_dosimetry"

        if record.source_type == "service_event":
            equipment = self._equipment_group(record)
            if equipment == "abc":
                return "abc_ad_hoc"
            if equipment == "linac":
                return "linac_ad_hoc"
            if equipment == "ct":
                return "ct_ad_hoc"
            return "ad_hoc_qa"

        equipment = self._equipment_group(record)
        frequency = self._collection_frequency_name(record)
        if equipment == "linac" and frequency == "monthly":
            return "linac_mqc"
        if equipment == "ct":
            if "quarterly" in title.lower():
                return "ct_quarterly"
            if frequency == "monthly" or "monthly" in title.lower():
                return "ct_monthly"
        if (record.title or "") == "ABC Weekly QC":
            return "abc_weekly"
        return "qa_session"

    def _group_label(self, record: SourceRecord, entry_type: str, context: TccContext) -> str:
        if entry_type == "linac_mqc":
            return "linac_monthly"
        if entry_type == "abc_weekly":
            return "abc_weekly"
        if entry_type == "abc_ad_hoc":
            return "abc_ad_hoc"
        if entry_type == "linac_ad_hoc":
            return "linac_ad_hoc"
        if entry_type == "ad_hoc_qa":
            return "ad_hoc_qa"
        if entry_type in {
            "ct_ad_hoc",
            "ct_monthly",
            "ct_quarterly",
            "monthly_dosimetry",
        }:
            return entry_type
        if (
            self._equipment_group(record) == "linac"
            and (record.title or "").startswith("Reference dosimetry :: ")
            and record.performed_at
            and (record.performed_at[:10], record.unit or "") in context.monthly_bucket_keys
        ):
            return "linac_monthly"
        return record.title or "qa_session"

    def _bucket_unit(self, record: SourceRecord, entry_type: str) -> str:
        if entry_type in {"abc_weekly", "abc_ad_hoc"}:
            return "ABC"
        if entry_type == "monthly_dosimetry":
            return "Monthly dosimetry"
        return record.unit or ""

    def _equipment_group(self, record: SourceRecord) -> str | None:
        unit = record.unit or ""
        if unit.startswith("LA"):
            return "linac"
        if unit.startswith("ABC"):
            return "abc"
        if unit.startswith("CT"):
            return "ct"
        return None

    def _collection_frequency_name(self, record: SourceRecord) -> str | None:
        collection = record.raw.get("unit_test_collection", {})
        if not isinstance(collection, dict):
            return None

        frequency = collection.get("frequency")
        if not isinstance(frequency, str):
            return None

        frequency_id = frequency.rstrip("/").rsplit("/", 1)[-1]
        if frequency_id == "3":
            return "monthly"

        return None

    def _resolve_entry_type(self, entry_type: str, records: list[SourceRecord]) -> str:
        if entry_type == "linac_mqc" and _looks_like_post_pmi(records):
            return "post_pmi"
        return entry_type

    def _additional_notable_prompts(self, entry_type: str, records: list[SourceRecord]) -> list[str]:
        if entry_type == "post_pmi":
            return ["Linac ready for clinical use. Re-enable energies and document on MOSAIQ."]
        return []

    def _map_performed_item(self, record: SourceRecord, entry_type: str) -> PerformedItem:
        if entry_type in {"linac_mqc", "post_pmi"}:
            return _map_linac_mqc_performed_item(record)
        if entry_type == "abc_weekly":
            return PerformedItem(category=record.unit or "ABC", label=record.title or record.remote_id)
        if entry_type in {"abc_ad_hoc", "linac_ad_hoc", "ct_ad_hoc"}:
            service_event = record.raw.get("service_event", {})
            if isinstance(service_event, dict):
                category = str(service_event.get("service_type_name") or "Service").strip()
                return PerformedItem(category=category, label=record.title or record.remote_id)

        title = record.title or record.remote_id
        return PerformedItem(category="QA", label=title)

    def _aggregate_performed_items(self, entry_type: str, items: list[PerformedItem]) -> list[PerformedItem]:
        if entry_type == "linac_mqc":
            return _aggregate_linac_mqc_items(items)
        if entry_type == "post_pmi":
            return _aggregate_post_pmi_items(items)
        return items

    def _notable_prompts(self, records: list[SourceRecord], entry_type: str) -> list[str]:
        if entry_type in {"abc_ad_hoc", "linac_ad_hoc", "ct_ad_hoc", "ad_hoc_qa"}:
            prompts = []
            for record in records:
                service_event = record.raw.get("service_event", {})
                if not isinstance(service_event, dict):
                    continue
                work_description = str(service_event.get("work_description", "")).strip()
                if work_description:
                    prompts.append(work_description)
            if prompts:
                return prompts
            return ["<no work description in source record>"]

        prompts: list[str] = []
        for record in records:
            session = record.raw.get("session", {})
            item = self._map_performed_item(record, entry_type)
            prompt_label = item.label if item.category in {"Dosimetry", "MLC"} else record.title or item.label
            for comment in session.get("comments", []):
                text = str(comment.get("comment", "")).strip()
                if text:
                    prompts.append(f"{prompt_label}\n  - {text}")
            if record.status == "flagged":
                prompts.append(f"{prompt_label}\n  - Review flagged results")
        if not prompts:
            prompts.append("<none in source records>")
        return prompts


def map_performed_item(record: SourceRecord, entry_type: str) -> PerformedItem:
    return RULES._map_performed_item(record, entry_type)


def aggregate_performed_items(entry_type: str, items: list[PerformedItem]) -> list[PerformedItem]:
    return RULES._aggregate_performed_items(entry_type, items)


def _map_linac_mqc_performed_item(record: SourceRecord) -> PerformedItem:
    title = (record.title or record.remote_id).strip()
    session_url = _session_site_url(record)

    if title.startswith("Linac Monthly :: Imaging :: CatPhan 503 :: "):
        scan = title.removeprefix("Linac Monthly :: Imaging :: CatPhan 503 :: ").strip()
        return PerformedItem(category="Imaging", label=scan, url=session_url)

    if title == "Winston Lutz :: eQA :: 6 MV":
        return PerformedItem(category="Winston Lutz", label="6 MV", url=session_url)

    if title == "Linac Monthly :: Mechanical":
        return PerformedItem(category="Mechanical", label="Machine mechanical measurements", url=session_url)

    if title == "Linac Monthly :: Safety and Functionality":
        return PerformedItem(
            category="Safety and Functionality",
            label="Mechanical drive and interlocks",
            url=session_url,
        )

    if title.startswith("Linac Monthly :: Geometry :: "):
        label = title.removeprefix("Linac Monthly :: Geometry :: ").strip()
        return PerformedItem(category="Geometry", label=label, url=session_url)

    if title.startswith("Linac Monthly :: Dosimetry :: "):
        label = title.removeprefix("Linac Monthly :: Dosimetry :: ").strip()
        return PerformedItem(category="Dosimetry", label=label, url=session_url)

    if title.startswith("Reference dosimetry :: "):
        return PerformedItem(category="Ad hoc", label=title, url=session_url)

    if title == "EPID image quality (PTW EPID QC)":
        return PerformedItem(category="EPID Image Quality", label="Contrast visibility", url=session_url)

    if title == "Linac Monthly :: MLC :: Leaf speed constancy":
        return PerformedItem(category="MLC", label="Leaf speed constancy", url=session_url)

    if title == "Linac Monthly :: MLC :: Sliding window fluence uniformity":
        return PerformedItem(category="MLC", label="Sliding window fluence uniformity", url=session_url)

    if title == "Linac Monthly :: MLC :: VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence":
        return PerformedItem(
            category="MLC",
            label="VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence",
            url=session_url,
        )

    if title.startswith("Linac Monthly :: MLC :: Picket Fence :: "):
        parts = [part.strip() for part in title.split("::")]
        if len(parts) >= 5:
            panel = parts[3]
            gantry = parts[4]
            return PerformedItem(category="MLC", label=f"Picket Fence: {gantry} {panel}", url=session_url)

    if title.startswith("Linac Monthly :: MLC :: "):
        label = title.removeprefix("Linac Monthly :: MLC :: ").strip()
        return PerformedItem(category="MLC", label=label, url=session_url)

    parts = [part.strip() for part in title.split("::")]
    if len(parts) == 1:
        return PerformedItem(category="QA", label=title, url=session_url)
    return PerformedItem(category=parts[0], label=" :: ".join(parts[1:]), url=session_url)


def _aggregate_linac_mqc_items(items: list[PerformedItem]) -> list[PerformedItem]:
    grouped: list[PerformedItem] = []
    handled: set[tuple[str, str]] = set()

    imaging_items = [item for item in items if item.category == "Imaging"]
    imaging_labels = {item.label for item in imaging_items}
    if imaging_labels:
        grouped.append(
            PerformedItem(
                category="Imaging",
                label="CatPhan 503",
                links=_ordered_links(imaging_items, ["MFOV CCW", "MFOV CW", "SFOV CCW", "SFOV CW"]),
            )
        )
        handled.update({("Imaging", label) for label in imaging_labels})

    winston_items = [item for item in items if item.category == "Winston Lutz"]
    if winston_items:
        grouped.append(PerformedItem(category="Winston Lutz", label="6 MV", url=winston_items[0].url))
        handled.update({(item.category, item.label) for item in winston_items})

    mechanical_items = [item for item in items if item.category == "Mechanical"]
    if mechanical_items:
        grouped.append(
            PerformedItem(
                category="Mechanical",
                label="Machine mechanical measurements",
                url=mechanical_items[0].url,
            )
        )
        handled.update({(item.category, item.label) for item in mechanical_items})

    safety_items = [item for item in items if item.category == "Safety and Functionality"]
    if safety_items:
        grouped.append(
            PerformedItem(
                category="Safety and Functionality",
                label="Mechanical drive and interlocks",
                url=safety_items[0].url,
            )
        )
        handled.update({(item.category, item.label) for item in safety_items})

    geometry_order = ["EPID scaling", "Light vs radiation", "Jaw drive accuracy"]
    geometry_items = [item for item in items if item.category == "Geometry"]
    geometry_seen = {item.label for item in geometry_items}
    geometry_labels = [label for label in geometry_order if label in geometry_seen]
    if geometry_labels:
        grouped.append(
            PerformedItem(
                category="Geometry",
                label=", ".join(_display_geometry_label(label) for label in geometry_labels),
                links=_ordered_links(geometry_items, geometry_order),
            )
        )
        handled.update({("Geometry", label) for label in geometry_labels})

    epid_items = [item for item in items if item.category == "EPID Image Quality"]
    if epid_items:
        grouped.append(
            PerformedItem(category="EPID Image Quality", label="Contrast visibility", url=epid_items[0].url)
        )
        handled.update({(item.category, item.label) for item in epid_items})

    mlc_items = [item for item in items if item.category == "MLC"]
    mlc_labels = {item.label for item in mlc_items}
    if mlc_labels:
        grouped.append(
            PerformedItem(
                category="MLC",
                label=_summarize_mlc_items(mlc_labels),
                links=[LinkRef(label=item.label, url=item.url) for item in mlc_items if item.url],
            )
        )
        handled.update({("MLC", label) for label in mlc_labels})

    for item in items:
        if (item.category, item.label) not in handled:
            grouped.append(item)

    return grouped


def _aggregate_post_pmi_items(items: list[PerformedItem]) -> list[PerformedItem]:
    grouped: list[PerformedItem] = []
    handled: set[tuple[str, str]] = set()

    if any(item.category == "Safety and Functionality" for item in items):
        grouped.append(
            PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks")
        )
        handled.update(
            {(item.category, item.label) for item in items if item.category == "Safety and Functionality"}
        )

    mlc_labels = {item.label for item in items if item.category == "MLC"}
    if mlc_labels:
        grouped.append(PerformedItem(category="MLC", label=_summarize_mlc_items(mlc_labels)))
        handled.update({("MLC", label) for label in mlc_labels})

    dosimetry_labels = {item.label for item in items if item.category == "Dosimetry"}
    if dosimetry_labels:
        if _has_full_post_pmi_dosimetry(dosimetry_labels):
            grouped.append(
                PerformedItem(
                    category="Dosimetry",
                    label="Photon and electron profile, output and energy constancy, all energies",
                )
            )
            handled.update(
                {
                    ("Dosimetry", label)
                    for label in dosimetry_labels
                    if label != "Quickcheck Constancy"
                }
            )

        if "Quickcheck Constancy" in dosimetry_labels:
            grouped.append(PerformedItem(category="Dosimetry", label="Quickcheck Constancy"))
            handled.add(("Dosimetry", "Quickcheck Constancy"))

    for item in items:
        if (item.category, item.label) not in handled:
            grouped.append(item)

    return grouped


def _display_geometry_label(label: str) -> str:
    if label == "Light vs radiation":
        return "light vs. radiation"
    if label == "Jaw drive accuracy":
        return "jaw drive accuracy"
    return label


def _summarize_mlc_items(labels: set[str]) -> str:
    summary: list[str] = []

    if "Leaf speed constancy" in labels:
        summary.append("Leaf speed constancy")

    if (
        "Sliding window fluence uniformity" in labels
        or "VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence" in labels
    ):
        summary.append("DRGS")

    if any(label.startswith("Picket Fence: ") for label in labels):
        summary.append("Picket fence by gantry angle")

    return ", ".join(summary)


def _has_full_post_pmi_dosimetry(labels: set[str]) -> bool:
    required = {
        "Photon profile constancy",
        "Electron profile constancy",
        "Output and relative dosimetry :: 6 MV",
        "Output and relative dosimetry :: 10 MV",
        "Output and energy constancy :: 6 MeV",
        "Output and energy constancy :: 8 MeV",
        "Output and energy constancy :: 10 MeV",
        "Output and energy constancy :: 12 MeV",
        "Output and energy constancy :: 15 MeV",
    }
    return required.issubset(labels)


def _looks_like_post_pmi(records: list[SourceRecord]) -> bool:
    titles = [(record.title or "").lower() for record in records]
    dosimetry_count = sum("linac monthly :: dosimetry ::" in title for title in titles)
    has_profiles = any("profile constancy" in title for title in titles)
    return dosimetry_count >= 3 and has_profiles


def _source_prefix(record: SourceRecord) -> str:
    if record.source_type == "service_event":
        return "service"
    return "qa"


def _service_event_performed_items(records: list[SourceRecord]) -> list[PerformedItem]:
    items: list[PerformedItem] = []
    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        problem_description = str(service_event.get("problem_description", "")).strip()
        work_description = str(service_event.get("work_description", "")).strip()
        work_summary, _ = _split_service_work_description(work_description)

        if problem_description:
            items.append(PerformedItem(category="Problem Description", label=problem_description))
        if work_summary:
            items.append(PerformedItem(category="Work description", label=work_summary))

    return items


def _service_event_detail_prompts(records: list[SourceRecord]) -> list[str]:
    prompts: list[str] = []
    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        work_description = str(service_event.get("work_description", "")).strip()
        _, detail = _split_service_work_description(work_description)
        if detail:
            prompts.append(detail)
    return prompts


def _service_event_metadata(records: list[SourceRecord]) -> dict[str, object]:
    return_to_service_by_url: dict[str, dict[str, object]] = {}

    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        for qa_session in service_event.get("return_to_service", []):
            if not isinstance(qa_session, dict):
                continue
            session_url = str(qa_session.get("session_url", "")).strip()
            if not session_url:
                continue
            stored = return_to_service_by_url.setdefault(
                session_url,
                {
                    "label": str(qa_session.get("label") or "Return to Service QA").strip(),
                    "session_url": session_url,
                    "qa_groups": [],
                },
            )
            groups = stored["qa_groups"]
            if not isinstance(groups, list):
                continue
            for qa_group in qa_session.get("qa_groups", []):
                normalized = str(qa_group).strip()
                if normalized and normalized not in groups:
                    groups.append(normalized)

    metadata: dict[str, object] = {}
    if return_to_service_by_url:
        metadata["return_to_service"] = list(return_to_service_by_url.values())
    return metadata


def _split_service_work_description(work_description: str) -> tuple[str, str]:
    normalized = work_description.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return "", ""

    parts = normalized.split("\n\n", 1)
    summary = parts[0].strip()
    detail = parts[1].strip() if len(parts) > 1 else ""
    return summary, detail


def _record_urls_metadata(records: list[SourceRecord], entry_type: str) -> dict[str, object]:
    urls: list[str] = []
    for record in records:
        url = _record_url(record)
        if url and url not in urls:
            urls.append(url)

    metadata: dict[str, object] = {}
    if entry_type == "linac_mqc":
        metadata["suppress_links_block"] = True
    if len(urls) == 1:
        metadata["url"] = urls[0]
    elif urls and entry_type != "linac_mqc":
        metadata["urls"] = urls
    return metadata


def _record_url(record: SourceRecord) -> str | None:
    if record.source_type == "service_event":
        service_event = record.raw.get("service_event", {})
        if isinstance(service_event, dict):
            url = str(service_event.get("event_url", "")).strip()
            return url or None
        return None

    session = record.raw.get("session", {})
    if isinstance(session, dict):
        url = str(session.get("site_url", "")).strip()
        if url:
            return url
    return None


def _session_site_url(record: SourceRecord) -> str | None:
    session = record.raw.get("session", {})
    if not isinstance(session, dict):
        return None
    url = str(session.get("site_url", "")).strip()
    return url or None


def _arpansa_calibration_item(record: SourceRecord) -> PerformedItem:
    if record.title == "ARPANSA Electrometer Calibration":
        label = (
            "ARPANSA Electrometer Calibration: pre- and post- UNITEST constancy, "
            "update documentation and spreadsheets with new certificate k_{elec}"
        )
    else:
        label = (
            "ARPANSA Calibration: pre- and post- imaging and ^{90}Sr dosimetry; "
            "update documentation with new calibration certificates"
        )
    return PerformedItem(category="QA", label=label)


def _monthly_dosimetry_items(records: list[SourceRecord]) -> list[PerformedItem]:
    buckets: dict[str, list[LinkRef]] = {
        "farmer": [],
        "pp": [],
        "semiflex": [],
        "electrometer": [],
    }
    standalone: dict[str, PerformedItem] = {}

    for record in records:
        url = _session_site_url(record)
        if record.title == "Thermometer Constancy":
            standalone["thermometer"] = PerformedItem(category="QA", label=record.title, url=url)
            continue
        if record.title == "Barometer Constancy":
            standalone["barometer"] = PerformedItem(category="QA", label=record.title, url=url)
            continue
        label, _serial = _monthly_equipment_label(record.unit)
        if not label or not url:
            continue
        if record.title == "Electrometer Constancy":
            bucket = "electrometer"
        elif "PPC40" in label or "Markus" in label:
            bucket = "pp"
        elif "31010" in label:
            bucket = "semiflex"
        else:
            bucket = "farmer"
        buckets[bucket].append(LinkRef(label=label, url=url))

    items: list[PerformedItem] = []
    definitions = [
        ("farmer", "Sr-90 Constancy, Leakage - Farmer chambers"),
        ("pp", "Sr-90 Constancy, Leakage - PP chambers"),
        ("semiflex", "Sr-90 Constancy, Leakage - Semiflex chambers"),
        ("electrometer", "Electrometer Constancy (UNITEST)"),
    ]
    for bucket, label in definitions:
        links = sorted(
            buckets[bucket],
            key=lambda link: _monthly_link_order(bucket, link.label),
        )
        if links:
            items.append(PerformedItem(category="QA", label=label, links=links))
    for key in ("thermometer", "barometer"):
        if key in standalone:
            items.append(standalone[key])
    return items


def _monthly_equipment_label(unit: str | None) -> tuple[str, int]:
    equipment, _, serial_text = (unit or "").partition(":")
    serial = int(serial_text.strip() or "0")
    normalized = " ".join(equipment.split())
    normalized = normalized.removeprefix("IBA ")
    replacements = {
        "FC-65G": "FC65-G",
        "FC65-G": "FC65-G",
        "PTW Adv Markus": "PTW Advanced Markus",
    }
    if normalized in replacements:
        normalized = replacements[normalized]
    return f"{normalized} {serial}", serial


def _label_serial(label: str) -> int:
    try:
        return int(label.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


def _monthly_link_order(bucket: str, label: str) -> tuple[int, int]:
    preferred = {
        "farmer": ["FC65-G 1782", "FC65-G 4698", "PTW 30013 11298"],
        "pp": ["PPC40 850", "PPC40 839", "PTW Advanced Markus 2348"],
        "semiflex": ["PTW 31010 7799", "PTW 31010 5811"],
    }.get(bucket, [])
    if label in preferred:
        return (0, preferred.index(label))
    return (1, _label_serial(label))


def _equipment_tags(unit: str | None) -> list[str]:
    equipment, separator, serial = (unit or "").partition(":")
    tags = [_compact_tag(equipment)]
    if separator and serial.strip():
        tags.append(_compact_tag(serial))
    return [tag for tag in tags if tag]


def _split_linac_service_tags(unit: str | None) -> list[str]:
    linac, separator, site = (unit or "").partition(" - ")
    if not separator:
        return [linac] if linac else []
    return [tag for tag in (linac.strip(), site.strip()) if tag]


def _destination_id(entry_type: str, records: list[SourceRecord]) -> str | None:
    if any(_is_la10_yamaru(record) for record in records):
        return "TCCLogbookMRLQA"
    return {
        "arpansa_calibration": "TCCLogbookARPANSACal",
        "monthly_dosimetry": "TCCLogbookMDos",
        "ct_ad_hoc": "TCCLogbookCTAdHocQA",
        "ct_monthly": "TCCLogbookCTMonthlyQA",
        "ct_quarterly": "TCCLogbookCTQuarterlyQA",
    }.get(entry_type)


def _is_la10_yamaru(record: SourceRecord) -> bool:
    unit = (record.unit or "").strip()
    site = (record.site or "").strip()
    if " - " in unit:
        unit, site = (part.strip() for part in unit.split(" - ", 1))
    return unit.casefold() == "la10" and site.casefold() == "yamaru"


def _ordered_links(items: list[PerformedItem], label_order: list[str]) -> list[LinkRef]:
    item_by_label = {item.label: item for item in items if item.url}
    links: list[LinkRef] = []
    for label in label_order:
        item = item_by_label.get(label)
        if item and item.url:
            links.append(LinkRef(label=label, url=item.url))
    for item in items:
        if item.url and item.label not in label_order:
            links.append(LinkRef(label=item.label, url=item.url))
    return links


def _compact_tag(value: str | None) -> str:
    if not value:
        return ""
    return value.replace(" ", "")


RULES = TccSimilarRules()
