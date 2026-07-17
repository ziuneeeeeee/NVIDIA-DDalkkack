import re

def normalize_text(text):
    if not text:
         return ""
    text = str(text)
    # Remove whitespaces, common punctuation, make lower
    text = re.sub(r'[\s,\.\'\"]', '', text).lower()
    return text

def grade_answer(user_answer, correct_answer):
    u = normalize_text(user_answer)
    c = normalize_text(correct_answer)
    if '$=' in c:
        c = c.split('$=')[-1].replace('$', '')

    return len(u) > 0 and u == c
