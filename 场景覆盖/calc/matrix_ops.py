# matrix_ops.py — 克制矩阵 numpy 原语
"""dict 矩阵 → ndarray, 攻/守效用向量, 点积。缺键 fail-closed。"""
from __future__ import annotations

import numpy as np

from 场景覆盖 import config as cfg


def to_ndarray(matrix: dict, row_types: list, col_types: list) -> np.ndarray:
    """把 {(row, col): val} 建成 (len(row) × len(col)) 矩阵。缺键 raise。"""
    n_r, n_c = len(row_types), len(col_types)
    out = np.zeros((n_r, n_c), dtype=float)
    for i, r in enumerate(row_types):
        for j, c in enumerate(col_types):
            key = (r, c)
            if key not in matrix:
                raise ValueError(
                    f"{cfg.PRINT_PREFIX_WARN} 矩阵缺键 {key!r}, "
                    f"业务真值应写入克制矩阵 Sheet, 不允许 1.0 兜底"
                )
            out[i, j] = float(matrix[key])
    return out


def atk_utility_vec(env_dist: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """攻方效用向量: v_i = Σ_j M[i,j] * env_j (属性 i 打环境)。"""
    return mat @ env_dist


def def_hit_vec(env_dist: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """守方挨打向量: h_j = Σ_i env_i * M[i,j] (环境打纯 j)。越大越疼。"""
    return env_dist @ mat


def expected_util(atk_dist: np.ndarray, def_dist: np.ndarray, mat: np.ndarray) -> float:
    """Σ_i Σ_j atk_i * def_j * M[i,j] = atk @ M @ def。"""
    return float(atk_dist @ mat @ def_dist)


def normalize_dist(arr: np.ndarray, name: str = "dist") -> np.ndarray:
    s = float(np.sum(arr))
    if s <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {name} sum={s}≤0, 业务数据缺失")
    if abs(s - 1.0) > cfg.PROGRAM_EPS:
        return arr / s
    return arr
