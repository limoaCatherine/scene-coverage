# distributions.py — 场景占比 (PVE/PVP/综合 × 属性/种族/体型)
from __future__ import annotations

from typing import Dict

from .env import EnvBundle, env_dist


def calc_distributions(bundle: EnvBundle) -> Dict:
    """返回 {lv: {env: {属性|体型|种族: {name: float}}}}"""
    result = {}
    for lv in bundle.levels:
        le = bundle.by_level[lv]
        result[lv] = {}
        for env in ("PVE", "PVP", "综合"):
            attr = env_dist(le, env, "attr")
            size = env_dist(le, env, "size")
            race = env_dist(le, env, "race")
            result[lv][env] = {
                "属性": {bundle.attr_types[i]: float(attr[i]) for i in range(len(bundle.attr_types))},
                "体型": {bundle.size_types[i]: float(size[i]) for i in range(len(bundle.size_types))},
                "种族": {bundle.race_types[i]: float(race[i]) for i in range(len(bundle.race_types))},
            }
    return result
