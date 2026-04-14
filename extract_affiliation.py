#!/usr/bin/env python3
"""
从 PDF 提取作者单位（affiliations）
核心策略：
1. 用 extract_words() 获取带 x/y 坐标的词列表
2. 用双栏自动检测（找最大 x 间隙）分离左/右栏
3. 同栏内按 y 分行、合并相邻词
4. 对 CamelCase 做分词还原
"""

import sys
import re
from pathlib import Path
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    print("[WARN] pdfplumber not installed")
    sys.exit(0)


ORG_KEYWORDS = [
    'university', 'institute', 'laboratory', 'lab', 'college', 'school',
    'department', 'center', 'centre', 'hospital', 'research', 'academy',
    'google', 'microsoft', 'meta', 'apple', 'amazon', 'ibm', 'intel',
    'nvidia', 'amd', 'qualcomm', 'samsung', 'huawei', 'tencent', 'alibaba',
    'bytedance', 'openai', 'anthropic', 'deepmind', 'mistral', 'cohere',
    'lg', 'baidu', 'didi', 'meituan', 'kuaishou',
    'mit', 'stanford', 'harvard', 'princeton', 'yale', 'berkeley', 'cornell',
    'oxford', 'cambridge', 'eth', 'epfl', 'inria', 'kit', 'tum',
    'tsinghua', 'peking', 'fudan', 'zhejiang', 'nanjing', 'shanghai',
    'seoul', 'kaist', 'postech', 'yonsei', 'kisti',
    'cmu', 'carnegie', 'gatech', 'purdue', 'uiuc', 'columbia', 'jhu',
    'caltech', 'ucla', 'ucsd', 'toronto', 'montreal', 'utsw',
    'national', 'max planck', 'fraunhofer',
]


def split_camel(text: str) -> str:
    parts = re.split(r'(?<=[a-z])(?=[A-Z])', text)
    small = {'of','the','and','in','for','to','a','an','on','at','by','with','from','or','its','as','is','are','s'}
    result = []
    for p in parts:
        sub = re.split(r'\b(' + '|'.join(small) + r')\b', p, flags=re.IGNORECASE)
        result.extend(x for x in sub if x)
    return ' '.join(result)


def clean_word(w: str) -> str:
    w = re.sub(r'[\†\‡\*\¹\²\³\⁴\⁵\⁶\⁷\⁸\⁹]', '', w)
    w = re.sub(r'-$', '', w)
    return split_camel(w).strip()


def is_org_word(text: str) -> bool:
    """全词边界匹配，不做子串匹配"""
    t = text.lower()
    for kw in ORG_KEYWORDS:
        # 构造单词边界正则（kw 本身是完整的词或词的一部分）
        # 允许 kw 是短语（如 "deep mind"）
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, t):
            return True
    return False


def find_column_gap(words: list, page_width: float) -> float:
    """自动检测双栏间隙位置，返回栏间边界 x 坐标"""
    if not words:
        return page_width / 2
    sorted_x = sorted(set(w['x0'] for w in words))
    if len(sorted_x) < 2:
        return page_width / 2
    # 找最大间隙
    max_gap = 0
    gap_x = page_width / 2
    sorted_x.sort()
    for i in range(len(sorted_x) - 1):
        gap = sorted_x[i+1] - sorted_x[i]
        if gap > max_gap and sorted_x[i] > page_width * 0.2 and sorted_x[i+1] < page_width * 0.8:
            max_gap = gap
            gap_x = (sorted_x[i] + sorted_x[i+1]) / 2
    return gap_x


def merge_org_phrase(words_in_line: list[dict]) -> str:
    """合并同一行的多个词"""
    # 先按 x 排序
    sorted_words = sorted(words_in_line, key=lambda x: x['x0'])
    combined = ''.join(w['text'] for w in sorted_words)
    # 去除行末连字符（换行标记）
    combined = re.sub(r'-$', '', combined)
    return clean_word(combined)


def merge_hyphen_continuation(phrases: list[str]) -> list[str]:
    """
    合并跨行的连字符词：
    'Repub-' + 'licof Korea2LG...' → 'Republic of Korea, LG Electronics...'
    """
    merged = []
    i = 0
    while i < len(phrases):
        p = phrases[i]
        # 如果当前短语以连字符结尾，尝试和下一个合并
        while i + 1 < len(phrases) and p.endswith('-'):
            p = p[:-1] + phrases[i + 1]
            i += 1
        merged.append(p)
        i += 1
    return merged


def extract_affiliations_from_pdf(pdf_path: Path) -> str:
    """
    主函数：返回 affiliations 字符串，格式 "单位1 | 单位2 | ..."
    """
    all_words = []
    column_gaps = []  # 每页的栏间隙

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                if not words:
                    continue
                gap = find_column_gap(words, page.width)
                column_gaps.append(gap)
                for w in words:
                    all_words.append({
                        'text': w['text'],
                        'page': page.page_number,
                        'y': w['top'],
                        'x0': w['x0'],
                        'page_gap': gap,
                        'page_width': page.width,
                    })
    except Exception as e:
        print(f"[WARN] pdf error: {e}")
        return ""

    if not all_words:
        return ""

    # 只保留含机构关键词的词
    org_candidates = [w for w in all_words if is_org_word(w['text'])]

    if not org_candidates:
        return ""

    # 按 page+y 分组同行（同栏），合并
    lines = defaultdict(list)
    for w in org_candidates:
        page = w['page']
        y_key = round(w['y'] / 10) * 10  # 10pt 容差
        col = 'L' if w['x0'] < w['page_gap'] else 'R'
        key = (page, col, y_key)
        lines[key].append(w)

    merged_phrases = []
    for key in sorted(lines.keys()):
        row_words = lines[key]
        phrase = merge_org_phrase(row_words)
        phrase = re.sub(r'^[\d\.\,\-\:\;]+', '', phrase).strip()
        phrase = re.sub(r'[\d\.\,\-\:\;]+$', '', phrase).strip()
        if len(phrase) > 4:
            merged_phrases.append(phrase)

    # 去重
    seen = set()
    unique = []
    for p in merged_phrases:
        k = re.sub(r'\s+', '', p).lower()
        if k not in seen and len(p) > 5:
            seen.add(k)
            unique.append(p)

    return ' | '.join(unique[:6])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 extract_affiliation.py <arxiv_id> [pdf_dir]")
        sys.exit(1)

    arxiv_id = sys.argv[1]
    pdf_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/wsg/hermes_path/arxiv_llm_quantization_paper_monitor/papers")
    pdf_path = pdf_dir / f"{arxiv_id}.pdf"

    print(f"=== Extracting: {arxiv_id} ===")
    result = extract_affiliations_from_pdf(pdf_path)
    print(f"Affiliations: {result if result else '(not found)'}")
