#!/usr/bin/env python3
"""Generate HTML nutrition plans from text sources and refresh the overview."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

PLAN_PATTERN = re.compile(r"^wochenplan_(\d{4}-\d{2}-\d{2})\.txt$")

STYLE_BLOCK = """  <style>
    :root {
      color-scheme: light;
    }
    body {
      font-family: Arial, sans-serif;
      line-height: 1.5;
      margin: 2rem auto;
      max-width: 860px;
      padding: 0 1rem;
    }
    header {
      margin-bottom: 2rem;
    }
    h1 {
      color: #1f4d3a;
      margin-bottom: 0.5rem;
    }
    h2 {
      color: #234f60;
      margin-top: 2rem;
    }
    h3 {
      margin-top: 1rem;
    }
    section {
      border-bottom: 1px solid #d0d7de;
      margin-bottom: 1.5rem;
      padding-bottom: 1.5rem;
    }
    ul {
      margin: 0.5rem 0 1rem 1.5rem;
    }
    li {
      margin: 0.25rem 0;
    }
    p {
      margin: 0.35rem 0 0.9rem;
    }
    footer {
      color: #4f6b6b;
      font-size: 0.85rem;
      margin-top: 3rem;
      text-align: center;
    }
  </style>"""

INDEX_STYLE_BLOCK = """  <style>
    body {
      font-family: Arial, sans-serif;
      line-height: 1.5;
      margin: 2rem auto;
      max-width: 680px;
      padding: 0 1rem;
    }
    h1 {
      color: #1f4d3a;
    }
    ul {
      list-style: none;
      margin: 2rem 0 0;
      padding: 0;
    }
    li {
      background: #f6f8fa;
      border: 1px solid #d0d7de;
      border-radius: 6px;
      margin: 0 0 1rem;
      padding: 0.75rem 1rem;
    }
    li a {
      color: #1f4d3a;
      font-weight: 600;
      text-decoration: none;
    }
    li a:hover {
      text-decoration: underline;
    }
    li span {
      color: #4f6b6b;
      display: block;
      font-size: 0.9rem;
      margin-top: 0.25rem;
    }
    .meta {
      color: #4f6b6b;
      font-size: 0.95rem;
      margin: 0.5rem 0 0;
    }
  </style>"""

SECTION_HEADINGS = {
    "Zwischenmahlzeiten-Empfehlung",
    "Getraenke-Tipp",
    "Allgemeine Hinweise",
}
EMPHASIS_HEADINGS = {
    "Zubereitungszeit",
    "Zubereitung",
    "Naehrwertfokus",
    "Batch-Tipp",
    "Thermomix",
}


@dataclass
class Plan:
    source: Path
    start_date: dt.date
    title: str
    body_html: str

    @property
    def iso_week(self) -> int:
        return self.start_date.isocalendar()[1]

    @property
    def iso_year(self) -> int:
        return self.start_date.isocalendar()[0]

    @property
    def end_date(self) -> dt.date:
        return self.start_date + dt.timedelta(days=6)

    @property
    def canonical_filename(self) -> str:
        return f"wochenplan_{self.start_date.isoformat()}.html"

    @property
    def kw_filename(self) -> str:
        return f"kw{self.iso_week:02d}-{self.iso_year}.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render nutrition plan HTML files and refresh the overview"
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Base directory containing plan text files",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip regenerating index.html",
    )
    return parser.parse_args()


def load_plans(base_dir: Path) -> List[Plan]:
    plans: List[Plan] = []
    for path in sorted(base_dir.glob("wochenplan_*.txt")):
        match = PLAN_PATTERN.match(path.name)
        if not match:
            continue
        start_date = dt.date.fromisoformat(match.group(1))
        raw_text = path.read_text(encoding="utf-8")
        title, body_html = convert_plan_text(raw_text, start_date)
        plans.append(Plan(source=path, start_date=start_date, title=title, body_html=body_html))
    return plans


def convert_plan_text(raw_text: str, start_date: dt.date) -> tuple[str, str]:
    lines = [line.strip() for line in raw_text.splitlines()]
    title = ""
    body_lines: List[str] = []
    for line in lines:
        if not title and line:
            title = line
            continue
        body_lines.append(line)
    if not title:
        raise ValueError("Plan text must contain a title on the first non-empty line")

    iso_year, iso_week, _ = start_date.isocalendar()

    parts: List[str] = []
    parts.append(f"  <h1>{html.escape(title)}</h1>")
    parts.append(f"  <p>KW {iso_week:02d}/{iso_year}</p>")

    open_section = False
    open_list = False
    in_ingredient_section = False
    current_ingredients: List[str] = []

    def ensure_section() -> None:
        nonlocal open_section
        if not open_section:
            parts.append("  <section>")
            open_section = True

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            parts.append("    </ul>")
            open_list = False

    def close_section() -> None:
        nonlocal open_section
        if open_section:
            close_list()
            parts.append("  </section>")
            open_section = False

    for line in body_lines:
        if not line:
            close_list()
            in_ingredient_section = False
            continue
        if line.startswith("Gericht "):
            close_section()
            parts.append("  <section>")
            parts.append(f"    <h2>{html.escape(line)}</h2>")
            open_section = True
            current_ingredients = []
            in_ingredient_section = False
            continue
        if line.startswith("- "):
            ensure_section()
            if not open_list:
                parts.append("    <ul>")
                open_list = True
            item_text = line[2:].strip()
            parts.append(f"      <li>{html.escape(item_text)}</li>")
            if in_ingredient_section:
                current_ingredients.append(item_text)
            continue
        if ":" in line:
            label, value = [segment.strip() for segment in line.split(":", 1)]
            if label in SECTION_HEADINGS:
                close_section()
                parts.append("  <section>")
                parts.append(f"    <h2>{html.escape(label)}</h2>")
                open_section = True
                if value:
                    parts.append(f"    <p>{html.escape(value)}</p>")
                in_ingredient_section = False
                current_ingredients = []
                continue
            if label == "Zutaten":
                ensure_section()
                close_list()
                parts.append(f"    <h3>{html.escape(label)}</h3>")
                if value:
                    parts.append(f"    <p>{html.escape(value)}</p>")
                in_ingredient_section = True
                current_ingredients = []
                continue
            if label in EMPHASIS_HEADINGS:
                ensure_section()
                close_list()
                if value:
                    parts.append(
                        f"    <p><strong>{html.escape(label)}:</strong> {html.escape(value)}</p>"
                    )
                else:
                    parts.append(f"    <p><strong>{html.escape(label)}:</strong></p>")
                if label == "Thermomix" and current_ingredients:
                    einkauf = ", ".join(html.escape(item) for item in current_ingredients)
                    parts.append(
                        f"    <p><strong>Einkaufsliste:</strong> {einkauf}</p>"
                    )
                    current_ingredients = []
                continue
            if value:
                ensure_section()
                close_list()
                parts.append(
                    f"    <p><strong>{html.escape(label)}:</strong> {html.escape(value)}</p>"
                )
                continue
        ensure_section()
        close_list()
        parts.append(f"    <p>{html.escape(line)}</p>")

    close_section()
    return title, "\n".join(parts)


def render_plan_html(plan: Plan) -> str:
    now = dt.datetime.now().astimezone()
    generated_on = now.strftime("%d.%m.%Y %H:%M %Z")
    lines: List[str] = [
        "<!DOCTYPE html>",
        "<html lang=\"de\">",
        "<head>",
        "  <meta charset=\"utf-8\" />",
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        f"  <title>{html.escape(plan.title)}</title>",
        STYLE_BLOCK,
        "</head>",
        "<body>",
        plan.body_html,
        "  <footer>",
        f"    Aktualisiert am {html.escape(generated_on)}",
        "  </footer>",
        "</body>",
        "</html>",
    ]
    return "\n".join(lines) + "\n"


def write_plan_files(plan: Plan, target_dir: Path) -> None:
    html_text = render_plan_html(plan)
    (target_dir / plan.canonical_filename).write_text(html_text, encoding="utf-8")
    (target_dir / plan.kw_filename).write_text(html_text, encoding="utf-8")


def render_index(plans: Sequence[Plan]) -> str:
    if not plans:
        raise ValueError("No plans found, cannot render index")
    sorted_plans = sorted(plans, key=lambda plan: plan.start_date, reverse=True)
    lines: List[str] = [
        "<!DOCTYPE html>",
        "<html lang=\"de\">",
        "<head>",
        "  <meta charset=\"utf-8\" />",
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        "  <title>Ernaehrungsplaene</title>",
        INDEX_STYLE_BLOCK,
        "</head>",
        "<body>",
    "  <h1>Wochenplan mit Rezepten</h1>",
        "  <ul>",
    ]
    for plan in sorted_plans:
        lines.extend(
            [
                "    <li>",
                f"      <a href=\"{plan.kw_filename}\">KW {plan.iso_week:02d}/{plan.iso_year}</a>",
                f"      <span>{html.escape(plan.title)}</span>",
                "    </li>",
            ]
        )
    lines.extend(["  </ul>", "</body>", "</html>"])
    return "\n".join(lines) + "\n"


def format_period_text(start_date: dt.date) -> str:
    end_date = start_date + dt.timedelta(days=6)
    return f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"


def main() -> None:
    args = parse_args()
    base_dir = args.target_dir.resolve()
    if not base_dir.is_dir():
        raise SystemExit(f"{base_dir} ist kein gueltiges Verzeichnis")

    plans = load_plans(base_dir)
    if not plans:
        raise SystemExit("Keine Wochenplaene gefunden (wochenplan_YYYY-MM-DD.txt)")

    for plan in plans:
        write_plan_files(plan, base_dir)

    if not args.no_index:
        index_html = render_index(plans)
        (base_dir / "index.html").write_text(index_html, encoding="utf-8")


if __name__ == "__main__":
    main()
