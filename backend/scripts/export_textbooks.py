#!/usr/bin/env python3
"""Export textbook pages from the widget_eurika database dump into markdown files.

Usage:
    # 1. Restore the dump to a local PostgreSQL:
    #    createdb eureka_teacher_dump
    #    pg_restore -d eureka_teacher_dump /path/to/eureka_rag_full.dump
    #
    # 2. Run this script:
    python scripts/export_textbooks.py \
        --db-url "postgresql://localhost/eureka_teacher_dump" \
        --output-dir ../teacher_staff/knowledge_base/

Each book becomes one .md file with YAML front-matter (subject, grade, grade_to,
book_title) and pages as ## sections. The files are organized by subject subdirectory.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg


def transliterate(text: str) -> str:
    """Simple Russian → Latin transliteration for safe filenames."""
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y",
        "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    result = []
    for ch in text.lower():
        result.append(mapping.get(ch, ch))
    # Replace non-alphanumeric with underscore, collapse multiples
    out = re.sub(r"[^a-z0-9]+", "_", "".join(result)).strip("_")
    return out


def export(db_url: str, output_dir: Path, skip_subjects: set[str] | None = None) -> None:
    skip_subjects = skip_subjects or set()

    print(f"Connecting to {db_url} ...")
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        # Get all documents with pages
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.doc_id, d.subject, d.grade, d.grade_to, d.book_title,
                       COUNT(p.pdf_page) AS page_count
                FROM documents d
                JOIN pages p ON d.doc_id = p.doc_id
                WHERE p.text_md IS NOT NULL AND p.text_md != ''
                GROUP BY d.doc_id, d.subject, d.grade, d.grade_to, d.book_title
                ORDER BY d.subject, d.grade, d.book_title
            """)
            docs = cur.fetchall()

        print(f"Found {len(docs)} documents with text_md content.")
        total_pages = 0
        files_written = 0

        for doc in docs:
            subject = doc["subject"]
            if subject in skip_subjects:
                continue

            # Create subject subdirectory
            subject_dir = output_dir / transliterate(subject)
            subject_dir.mkdir(parents=True, exist_ok=True)

            # Fetch pages for this document
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT pdf_page, book_page, text_md
                    FROM pages
                    WHERE doc_id = %s AND text_md IS NOT NULL AND text_md != ''
                    ORDER BY pdf_page
                """, (doc["doc_id"],))
                pages = cur.fetchall()

            if not pages:
                continue

            # Build markdown file
            book_title = doc["book_title"] or f"book_{doc['doc_id']}"
            grade = doc["grade"]
            grade_to = doc["grade_to"]

            lines = [
                "---",
                f"subject: {subject}",
                f"grade: {grade}",
                f"grade_to: {grade_to}",
                f"book_title: {book_title}",
                "---",
                "",
            ]

            for page in pages:
                page_num = page["book_page"] or page["pdf_page"]
                lines.append(f"## Страница {page_num}")
                lines.append("")
                lines.append(page["text_md"].strip())
                lines.append("")

            # Write file
            filename = f"{transliterate(book_title)}.md"
            filepath = subject_dir / filename
            filepath.write_text("\n".join(lines), encoding="utf-8")

            total_pages += len(pages)
            files_written += 1
            print(f"  [{files_written}] {subject} / {book_title}: {len(pages)} pages → {filepath.name}")

    print(f"\nDone: {files_written} files, {total_pages} pages total.")
    print(f"Output: {output_dir.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Export textbook pages from dump to markdown files")
    parser.add_argument("--db-url", required=True, help="PostgreSQL connection string for restored dump")
    parser.add_argument(
        "--output-dir", default="../teacher_staff/knowledge_base/",
        help="Output directory for markdown files (default: ../teacher_staff/knowledge_base/)",
    )
    parser.add_argument(
        "--skip-subjects", nargs="*", default=[],
        help="Subjects to skip (e.g., ИЗО Музыка)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    export(args.db_url, output_dir, skip_subjects=set(args.skip_subjects))


if __name__ == "__main__":
    main()
