"""Conservative candidate hints; source metadata remains untrusted."""

import re


def classify(title: str, description: str = "") -> tuple[str, str]:
    text = (title + " " + description).casefold()
    exam = bool(re.search(r"\b(exam\w*|\w*klausur\w*|\w*prüfung\w*|\w*pruefung\w*)", text))
    mock = bool(
        re.search(r"\b(mock|practice exam|sample exam|probeklausur|übungsklausur)\w*", text)
    )
    solution = bool(re.search(r"\b(solution\w*|\w*lösung\w*|\w*loesung\w*|answer key)", text))
    summary = bool(
        re.search(
            r"\b(summary|summaries|zusammenfassung|cheat[ -]?sheet|formula sheet|"
            r"formelsammlung|spickzettel)\w*",
            text,
        )
    )
    if summary and re.search(
        r"\b(summary|summaries|zusammenfassung|cheat[ -]?sheet|formula sheet|"
        r"formelsammlung|spickzettel)\w*",
        title.casefold(),
    ):
        return "summaries", "summary"
    if exam or mock:
        return "exams", "solution" if solution else "mock" if mock else "exam"
    if summary:
        return "summaries", "summary"
    return "other", "other"
