import re

CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨"


def extract_mcq_options(question_text):
    """Parse '①-3 ②-1 ③0 ...' style options out of a question.
    Returns [(1, '-3'), (2, '-1'), ...] in order, or None if not multiple-choice."""
    if not question_text:
        return None
    marks = [(m.start(), CIRCLED_DIGITS.index(m.group()) + 1) for m in re.finditer(f"[{CIRCLED_DIGITS}]", question_text)]
    if len(marks) < 2:
        return None
    options = []
    for i, (pos, num) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(question_text)
        options.append((num, question_text[pos + 1:end].strip()))
    return options


def resolve_mcq_answer(question_text, user_answer):
    """If the question is multiple-choice and the student answered with just an option number
    (e.g. '2', '②', '2번'), resolve it to that option's actual value so grading compares values, not indices."""
    options = extract_mcq_options(question_text)
    if not options:
        return user_answer
    options_map = dict(options)

    s = str(user_answer or "").strip()
    idx = None
    if len(s) == 1 and s in CIRCLED_DIGITS:
        idx = CIRCLED_DIGITS.index(s) + 1
    else:
        m = re.fullmatch(r"([1-9])\s*(번|\.)?", s)
        if m:
            idx = int(m.group(1))

    if idx is not None and idx in options_map:
        return options_map[idx]
    return user_answer
