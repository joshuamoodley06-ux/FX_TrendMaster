from __future__ import annotations

from range_library_memory import daily_inherited_doctrine as inherited


class _Pipeline:
    @staticmethod
    def stable_json(value):
        import json
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def sha(value):
        import hashlib
        return hashlib.sha256(_Pipeline.stable_json(value).encode()).hexdigest()


def _master():
    return {
        "trusted_root": {
            "node_type": "SYMBOL",
            "children": [
                {
                    "node_type": "RANGE",
                    "id": "weekly-1",
                    "structure_layer": "WEEKLY",
                    "children": [
                        {
                            "node_type": "RANGE",
                            "id": "daily-1",
                            "structure_layer": "DAILY",
                            "children": [],
                        }
                    ],
                }
            ],
        }
    }


def test_inherited_daily_output_projects_without_registering_a_daily_approval_script() -> None:
    master = _master()
    counts = inherited._project_stage(
        pipeline=_Pipeline(),
        master_map=master,
        stage_key="daily_structure",
        source_key="weekly_structure",
        source_version={"version_id": "weekly-v3", "version_label": "3"},
        outputs=[
            {
                "canonical_range_id": "daily-1",
                "processing_status": "COMPLETE",
                "payload": {
                    "chronology": "RL_TO_RH",
                    "bos_direction": "BOS_UP",
                },
            }
        ],
    )

    daily = master["trusted_root"]["children"][0]["children"][0]
    memory = daily["analysis_enrichments"]["daily_structure"]
    assert counts == {"outputs": 1, "complete": 1, "pending": 0, "needs_review": 0}
    assert memory["processing_status"] == "COMPLETE"
    assert memory["payload"]["bos_direction"] == "BOS_UP"
    assert memory["payload"]["inherited_from_weekly_script"] == "weekly_structure"
    assert memory["adapter_key"] == inherited.INHERITED_ADAPTER


def test_hierarchy_aliases_use_daily_results_without_touching_weekly_node() -> None:
    master = _master()
    daily = master["trusted_root"]["children"][0]["children"][0]
    daily["analysis_enrichments"] = {
        "daily_structure": {
            "version_id": "inherited:weekly-v3",
            "version_label": "3",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "structure",
            "processing_status": "COMPLETE",
            "payload": {"chronology": "RH_TO_RL", "bos_direction": "BOS_DOWN"},
        },
        "daily_reclaim": {
            "version_id": "inherited:weekly-reclaim-v2",
            "version_label": "2",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "reclaim",
            "processing_status": "COMPLETE",
            "payload": {"reclaim_status": "ABANDONED_THEN_RECLAIMED"},
        },
        "daily_profile_classification": {
            "version_id": "inherited:weekly-profile-v1",
            "version_label": "1",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "profile",
            "processing_status": "COMPLETE",
            "payload": {"profile_classification": "S&D", "profile_badge": "◆ S&D"},
        },
    }

    inherited._project_hierarchy_aliases(master)

    weekly = master["trusted_root"]["children"][0]
    assert "analysis_enrichments" not in weekly
    assert daily["analysis_enrichments"]["weekly_structure"]["payload"]["bos_direction"] == "BOS_DOWN"
    assert daily["analysis_enrichments"]["weekly_reclaim"]["payload"]["reclaim_status"] == "ABANDONED_THEN_RECLAIMED"
    assert daily["analysis_enrichments"]["weekly_profile_classification"]["payload"]["profile_badge"] == "◆ S&D"


def test_clear_removes_only_inherited_daily_and_renderer_alias_keys() -> None:
    master = _master()
    daily = master["trusted_root"]["children"][0]["children"][0]
    daily["analysis_enrichments"] = {
        "daily_structure": {"payload": {}},
        "weekly_structure": {"payload": {}},
        "other_research": {"payload": {"keep": True}},
    }

    inherited._clear_inherited_daily_memory(master)

    assert daily["analysis_enrichments"] == {
        "other_research": {"payload": {"keep": True}},
    }
