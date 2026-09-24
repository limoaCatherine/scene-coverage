# matrices.py — 克制矩阵 Sheet 读取
from typing import Dict, List, Tuple

from 场景覆盖 import config as cfg


def _find_all_keyword_cells(ws, keywords: List[str],
                            max_rows=None) -> Dict[str, Tuple[int, int]]:
    """全工作表扫描关键词单元格,返回 {keyword: (row, col)}。"""
    if max_rows is None:
        max_rows = cfg.KEYWORD_SEARCH_MAX_ROWS
    found: Dict[str, Tuple[int, int]] = {}
    keywords_left = set(keywords)
    for r in range(1, min(ws.max_row + 1, max_rows + 1)):
        for c in range(1, min(ws.max_column + 1, cfg.MAX_SEARCH_COL)):
            val = ws.cell(row=r, column=c).value
            if val is None:
                continue
            s = str(val).strip()
            for kw in list(keywords_left):
                if kw in s:
                    found[kw] = (r, c)
                    keywords_left.discard(kw)
            if not keywords_left:
                break
        if not keywords_left:
            break

    if keywords_left:
        raise cfg.ConfigDriftError(
            f"克制矩阵 Sheet 未找到以下矩阵标题: {sorted(keywords_left)}. "
            f"业务真值应写入 A1/P1/A14/J14 等标题单元格,不允许读取器兜底"
        )
    return found


def _extract_attr_cols(ws, header_row, start_col=2):
    """从矩阵表头行提取属性列名 (反向白名单 + 简称归一)。"""
    attr_list = []
    for c in range(start_col, ws.max_column + 1):
        val = ws.cell(row=header_row, column=c).value
        if val is None:
            break
        s = str(val).strip()
        if not s:
            break
        if s in cfg.ATTR_TYPES:
            attr_list.append(s)
        elif s in cfg.ATTR_NAME_NORMALIZE:
            attr_list.append(cfg.ATTR_NAME_NORMALIZE[s])
        else:
            break
    return attr_list[:10]


def _extract_size_cols(ws, header_row, start_col=2):
    """从矩阵表头行提取 3 体型列名。"""
    size_list = []
    for c in range(start_col, min(ws.max_column + 1, start_col + 3)):
        val = ws.cell(row=header_row, column=c).value
        if val is None:
            break
        s = str(val).strip()
        if s in ("小型", "小", "小体型"):
            size_list.append("小体型")
        elif s in ("中型", "中", "中体型"):
            size_list.append("中体型")
        elif s in ("大型", "大", "大体型"):
            size_list.append("大体型")
        else:
            break
    if len(size_list) < 3:
        raise cfg.ConfigDriftError(
            f"体型矩阵表头 R{header_row}C{start_col} 起仅解析到 {len(size_list)} 个体型列 "
            f"({size_list}), 预期 3 列(小/中/大)。业务真值应写入克制矩阵 Sheet, 不允许兜底"
        )
    return size_list


def _is_title_row(val):
    """判定某行是否是矩阵区段标题 (用于数据行终止)。"""
    if val is None:
        return False
    s = str(val).strip()
    return any(kw in s for kw in (
        "PVE属性", "PVP属性", "PVE体型", "PVP体型", "PVE种族", "PVP种族",
        "武器/体型", "属性攻方", "属性守方", "种族效用",
    ))


def read_all_matrices(wb):
    """读取克制矩阵 Sheet 中的 PVE/PVP 属性/体型克制矩阵。"""
    ws = wb[cfg.MATRIX_SHEET]
    keywords = ["PVE属性克制", "PVP属性克制", "PVE体型克制", "PVP体型克制"]
    starts = _find_all_keyword_cells(ws, keywords)
    cfg.qprint(f"{cfg.PRINT_PREFIX_READ} 矩阵读取")

    matrices = {}
    for keyword, (title_row, title_col) in starts.items():
        header_row = title_row + 1
        data_start_row = header_row + 1
        data_value_col_start = title_col + 1

        if "体型" in keyword:
            size_list = _extract_size_cols(ws, header_row, start_col=data_value_col_start)
            weapon_list = []
            matrix = {}
            consecutive_empty = 0
            for r in range(data_start_row, ws.max_row + 1):
                weapon = ws.cell(row=r, column=title_col).value
                if weapon is None or str(weapon).strip() == "":
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    continue
                if _is_title_row(weapon):
                    break
                consecutive_empty = 0
                weapon = str(weapon).strip()
                weapon_list.append(weapon)
                for idx, sz in enumerate(size_list):
                    val = ws.cell(row=r, column=data_value_col_start + idx).value
                    if val is not None:
                        try:
                            matrix[(weapon, sz)] = float(val)
                        except ValueError:
                            pass
            cfg.qprint(f"  {cfg.PRINT_PREFIX_MATRIX_MERGE} {keyword}: "
                       f"{len(weapon_list)} 武器 (独立, 不合并)")
            matrices[keyword] = (weapon_list, size_list, matrix)
        else:
            attr_list = _extract_attr_cols(ws, header_row, start_col=data_value_col_start)
            if len(attr_list) < 10:
                raise cfg.ConfigDriftError(
                    f"{keyword} 表头 R{header_row}C{data_value_col_start} 起仅解析到 "
                    f"{len(attr_list)} 个属性列 ({attr_list}), 预期 10 列。"
                    f"业务真值应写入克制矩阵 Sheet, 不允许兜底"
                )
            matrix = {}
            consecutive_empty = 0
            for r in range(data_start_row, ws.max_row + 1):
                atk = ws.cell(row=r, column=title_col).value
                if atk is None or str(atk).strip() == "":
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    continue
                if _is_title_row(atk):
                    break
                consecutive_empty = 0
                atk = str(atk).strip()
                for idx, defe in enumerate(attr_list):
                    val = ws.cell(row=r, column=data_value_col_start + idx).value
                    if val is not None:
                        try:
                            matrix[(atk, defe)] = float(val)
                        except ValueError:
                            pass
            matrices[keyword] = (attr_list, matrix)
    return matrices
