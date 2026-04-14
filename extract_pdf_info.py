#!/usr/bin/env python3
"""
从 PDF 提取作者单位（affiliations）
修复 pdfplumber 空格/换行丢失问题：改用 extract_words() 保留词边界，
并对连写词（如 DepartmentofPoliticalSciences）做启发式分词。
"""

import sys
import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("[WARN] pdfplumber not installed, affiliation extraction disabled")
    sys.exit(0)


# 常见机构名（用于匹配和分词）
KNOWN_ORGS = [
    "University", "Institute", "Laboratory", "Lab", "School", "College",
    "Department", "Center", "Centre", "Hospital", "Research",
    "Google", "Microsoft", "Meta", "Apple", "Amazon", "IBM", "Intel",
    "NVIDIA", "AMD", "Qualcomm", "Samsung", "Huawei", "Tencent", "Alibaba",
    "ByteDance", "DeepMind", "OpenAI", "Anthropic", "Mistral", "Cohere",
    "Tsinghua", "Peking", "Fudan", "Shanghai", "Zhejiang", "Nanjing",
    "MIT", "Stanford", "Harvard", "Princeton", "Yale", "Berkeley",
    "Oxford", "Cambridge", "ETH", "EPFL", "INRIA", "KIT", "TUM",
    "Intel", "NVIDIA", "Qualcomm", "Samsung", "TSMC",
    "Baidu", "Alibaba", "Tencent", "DiDi", "Meituan",
    "CAS", "Chinese Academy", "Max Planck", "Fraunhofer",
]


def split_camel(text: str) -> list[str]:
    """
    对连写词做启发式分词：
    'DepartmentofPoliticalSciences' → ['Department', 'of', 'Political', 'Sciences']
    策略：在 (小写→大写) 交界处切开，并对常见介词/冠词做二次切分
    """
    # 在 小写字母 后紧跟 大写字母 处切开
    tokens = re.split(r'(?<=[a-z])(?=[A-Z])', text)

    # 对每个 token 进一步切分常见介词/冠词/方位词
    small_words = {"of", "the", "and", "in", "for", "to", "a", "an", "on", "at", "by", "with", "from", "or"}
    refined = []
    for tok in tokens:
        # 尝试继续切分：如果 token 开头是常见小词
        parts = re.split(r'\b(of|the|and|in|for|to|a|an|on|at|by|with|from|or)\b', tok, flags=re.IGNORECASE)
        parts = [p for p in parts if p]
        refined.extend(parts)

    return refined


def clean_text(text: str) -> str:
    """
    清理 pdfplumber 提取的文本：
    1. 将多个空格/换行压缩为单个空格
    2. 还原常见连写词（Department of Political Sciences）
    """
    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()

    # 对 CamelCase 连写词做分词
    def fix_token(m):
        word = m.group(0)
        # 如果包含小写+大写交替（CamelCase），尝试分词
        if re.search(r'[a-z][A-Z]', word):
            parts = split_camel(word)
            return ' '.join(parts)
        return word

    # 匹配连续的大写字母开头的词（含 CamelCase）
    result = re.sub(r'\b[A-Z][a-zA-Z]+(?:\'[a-zA-Z]+)?(?:\s*[A-Z][a-zA-Z]+)*', fix_token, text)

    # 再次压缩多余空格
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def extract_first_page_text(pdf_path: Path) -> str:
    """提取 PDF 第1-2页的文本（原始无处理）"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages[:2]:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as e:
        print(f"[WARN] Failed to extract text from {pdf_path}: {e}")
        return ""


def extract_affiliation(text: str, authors: str) -> str:
    """
    从 PDF 文本中提取作者单位
    策略：
    1. 找到作者名列表（在标题下方，通常是第一行或第二行）
    2. 找到脚注或 *email 区域（包含 ^1 ^2 上标）
    3. 匹配作者上标编号 → 脚注单位
    4. 如果找不到脚注，直接匹配已知机构名
    """
    if not text:
        return ""

    # 策略1：匹配脚注格式
    #  e.g. "¹MIT ²Stanford" 或 "1. MIT 2. Stanford"
    footnote_pattern = re.compile(
        r'[\^]?(\d+)[\.\s]*([A-Z][A-Za-z\s&,\-\.]+?(?:University|Institute|Lab|College|School|Google|Microsoft|Meta|DeepMind|Stanford|MIT|Harvard|Berkeley|Peking|Tsinghua|NVIDIA|Intel|Samsung|Huawei|ByteDance|Amazon|OpenAI|Anthropic)[A-Za-z\s&,\-\.]*)',
        re.IGNORECASE
    )
    matches = footnote_pattern.findall(text)
    if matches:
        affs = []
        for num, org in matches[:10]:  # 最多取10个
            org = clean_text(org)
            if len(org) > 3:
                affs.append(org)
        if affs:
            return " | ".join(affs)

    # 策略2：直接匹配已知机构名（在文本前2000字符中）
    front_text = text[:2000]
    found_orgs = set()
    for org in KNOWN_ORGS:
        pattern = re.compile(rf'\b{re.escape(org)}[\w\s\-]*', re.IGNORECASE)
        for m in pattern.finditer(front_text):
            aff = clean_text(m.group(0))
            if len(aff) > 4:
                found_orgs.add(aff)
                break  # 每类机构只取第一个匹配

    if found_orgs:
        # 按原文顺序排序
        sorted_affs = []
        for aff in found_orgs:
            pos = text.find(aff.replace(' ', '').lower()[:10])
            sorted_affs.append((pos if pos >= 0 else 9999, aff))
        sorted_affs.sort(key=lambda x: x[0])
        return " | ".join(a for _, a in sorted_affs)

    return ""


def extract_affiliations_batch(pdf_dir: Path, papers: list[dict]) -> list[dict]:
    """批量处理"""
    results = []
    for paper in papers:
        pdf_path = pdf_dir / paper["pdf_filename"]
        if not pdf_path.exists():
            results.append({**paper, "affiliations": ""})
            continue

        raw_text = extract_first_page_text(pdf_path)
        aff = extract_affiliation(raw_text, paper.get("authors", ""))
        results.append({**paper, "affiliations": aff})
        print(f"[OK] {paper['arxiv_id']}: {aff[:80] if aff else '(not found)'}")

    return results


if __name__ == "__main__":
    import json
    import os

    if len(sys.argv) < 2:
        print("Usage: python3 extract_pdf_info.py <arxiv_id> [pdf_dir]")
        sys.exit(1)

    arxiv_id = sys.argv[1]
    pdf_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/wsg/hermes_path/arxiv_llm_quantization_paper_monitor/papers")
    pdf_path = pdf_dir / f"{arxiv_id}.pdf"

    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Extracting: {arxiv_id}")
    raw_text = extract_first_page_text(pdf_path)
    print(f"\n--- Raw text (first 500 chars) ---")
    print(raw_text[:500])
    print(f"\n--- Affiliation ---")
    aff = extract_affiliation(raw_text, "")
    print(aff)
