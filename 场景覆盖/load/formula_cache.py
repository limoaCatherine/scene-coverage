# formula_cache.py — openpyxl save 后重算并注入公式 <v> 缓存
import os
import re
import tempfile
import zipfile

from 场景覆盖 import config as cfg


def refill_formula_cache(xlsx_path):
    """Inject computed values into <v> tags of formula cells.

    openpyxl save 会清空公式 <v> 缓存 (不可逆), 必须用 formulas 库重算后注入.
    只写 <v>...</v>, 不动 <f>FORMULA</f>(Excel 打开会重算覆盖).
    """
    try:
        import formulas
    except ImportError:
        cfg.qprint(f'{cfg.PRINT_PREFIX_WARN} refill: formulas library not installed, skipping')
        return 0

    # 框架含 UDF（如 分段成长投放）时 formulas 会直接失败；box 上不做 COM，软跳过。
    cfg.qprint(f'[refill] loading {os.path.basename(xlsx_path)} ...')
    try:
        xl = formulas.ExcelModel().loads(xlsx_path).finish()
        sol = xl.calculate()
    except Exception as e:
        cfg.qprint(f'{cfg.PRINT_PREFIX_WARN} refill: formulas 跳过 ({type(e).__name__}: {e})；'
                   f'地图价值等将走 formula_proxy 近似')
        return 0
    cfg.qprint(f'[refill] solved {len(sol)} formula values')

    cache = {}
    for k, v in sol.items():
        m = re.match(r"'\[(.+?)\](.+?)'!([A-Z]+\d+)$", k)
        if not m:
            continue
        sheet_name, cell_ref = m.group(2), m.group(3)
        try:
            arr = v.value if hasattr(v, 'value') else v
            if hasattr(arr, 'tolist'):
                arr = arr.tolist()
            while isinstance(arr, list) and len(arr) == 1:
                arr = arr[0]
            if isinstance(arr, list) and len(arr) > 1:
                arr = arr[0]
            scalar = arr
        except Exception:
            continue
        if scalar is None:
            continue
        if isinstance(scalar, bool):
            cache[(sheet_name, cell_ref)] = ('1' if scalar else '0', 'b')
        elif isinstance(scalar, (int, float)):
            cache[(sheet_name, cell_ref)] = (repr(float(scalar)), 'n')
        elif isinstance(scalar, str):
            cache[(sheet_name, cell_ref)] = (scalar, 'str')

    with zipfile.ZipFile(xlsx_path, 'r') as z:
        wb_xml = z.read('xl/workbook.xml').decode('utf-8')
        rels_xml = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    sheet_pairs = re.findall(
        r'<sheet\s[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb_xml)
    all_rels = re.findall(r'<Relationship[^>]+/>', rels_xml)
    rid_to_target = {}
    for rel in all_rels:
        tm = re.search(r'Target="([^"]+)"', rel)
        im = re.search(r'Id="(rId\d+)"', rel)
        typem = re.search(r'Type="([^"]+)"', rel)
        if tm and im and typem and 'worksheet' in typem.group(1):
            target = tm.group(1).lstrip('/')
            if not target.startswith('xl/'):
                target = 'xl/' + target
            rid_to_target[im.group(1)] = target
    name_to_path = {n: rid_to_target[r]
                    for n, r in sheet_pairs if r in rid_to_target}

    n_filled_ref = [0]
    n_skipped_ref = [0]
    new_contents = {}
    for sheet_name, path in name_to_path.items():
        with zipfile.ZipFile(xlsx_path, 'r') as z:
            xml = z.read(path).decode('utf-8')

        def make_repl(sn, filled_ref, skipped_ref):
            def repl(m):
                cell_tag = m.group(0)
                cm = re.search(r'r="([A-Z]+\d+)"', cell_tag)
                if not cm:
                    return cell_tag
                key = (sn, cm.group(1))
                if key not in cache:
                    skipped_ref[0] += 1
                    return cell_tag
                val_str, type_str = cache[key]
                new_tag = cell_tag
                if type_str == 'str':
                    if 't="' in new_tag:
                        new_tag = re.sub(r't="[^"]*"', 't="str"',
                                         new_tag, count=1)
                    else:
                        new_tag = re.sub(r'(<c r="[^"]+")',
                                         r'\1 t="str"',
                                         new_tag, count=1)
                new_tag = re.sub(r'<v></v>',
                                 f'<v>{val_str}</v>',
                                 new_tag, count=1)
                if new_tag != cell_tag:
                    filled_ref[0] += 1
                return new_tag
            return repl

        new_xml = re.sub(
            r'<c\s[^>]*>\s*<f[^>]*>[^<]*</f>\s*<v></v>\s*</c>',
            make_repl(sheet_name, n_filled_ref, n_skipped_ref), xml)
        if new_xml != xml:
            new_contents[path] = new_xml.encode('utf-8')

    if not new_contents:
        cfg.qprint(f'[refill] no formula cells need updating '
                   f'(already cached or no formulas)')
        return 0

    fd, tmp = tempfile.mkstemp(suffix='.xlsx',
                                dir=os.path.dirname(xlsx_path))
    os.close(fd)
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as zin, \
             zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in new_contents:
                    zout.writestr(item, new_contents[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))
        os.replace(tmp, xlsx_path)
        cfg.qprint(f'[refill] injected {n_filled_ref[0]} values, '
                   f'skipped {n_skipped_ref[0]}')
    except Exception as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        print(f'{cfg.PRINT_PREFIX_WARN} refill: write failed: {e}')
    return n_filled_ref[0]
