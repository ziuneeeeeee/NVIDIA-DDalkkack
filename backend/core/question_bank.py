import json
import random
from pathlib import Path

class QuestionBank:
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.questions = []
        self.load_all_grades()

    def load_all_grades(self):
        if self.data_path.exists():
            with open(self.data_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
        else:
            self.questions = []
        self._by_id = {q['id']: q for q in self.questions}
            
    @staticmethod
    def _fill(matched, count, *fallback_pools):
        """Use every matched question first; only pad the shortfall from broader
        fallback pools instead of discarding a good-but-short match entirely."""
        if len(matched) >= count:
            return random.sample(matched, count)

        result = list(matched)
        used_ids = {q['id'] for q in matched}
        for fp in fallback_pools:
            if len(result) >= count:
                break
            remaining = [q for q in fp if q['id'] not in used_ids]
            need = count - len(result)
            if remaining:
                filler = random.sample(remaining, min(need, len(remaining)))
                result.extend(filler)
                used_ids.update(q['id'] for q in filler)
        return result

    def get_by_id(self, question_id):
        return self._by_id.get(question_id)

    def get_by_ids(self, question_ids):
        return [self._by_id[qid] for qid in question_ids if qid in self._by_id]

    def has_keyword_match(self, grade, topic_name):
        """Check whether a keyword matches anything at all for a grade, independent of
        difficulty/count, so the caller can warn the student before silently falling back."""
        keyword = (topic_name or '').strip()
        if not keyword:
            return True

        kw = keyword.lower()
        pool = [q for q in self.questions if q.get('grade') == grade] if grade else self.questions
        return any(
            kw in str(q.get(field) or '').lower()
            for q in pool
            for field in ('topic_name', 'sector2', 'sector1')
        )

    def search(self, grade=None, topic_name=None, sector2=None, sector1=None, difficulty=None, count=1):
        # Grade is a hard constraint (the student picked their own grade level);
        # difficulty/topic are relaxed before grade ever is.
        base = self.questions
        if grade:
            graded = [q for q in base if q.get('grade') == grade]
            if graded:
                base = graded

        pool = base
        if difficulty:
            pool = [q for q in pool if str(q.get('difficulty')) == str(difficulty)]

        # Free-text keyword rarely matches an official topic_name exactly, so
        # relax from topic_name -> sector2 -> sector1 using substring matching.
        keyword = (topic_name or '').strip()
        if keyword:
            kw = keyword.lower()
            for field in ('topic_name', 'sector2', 'sector1'):
                candidates = [q for q in pool if kw in str(q.get(field) or '').lower()]
                if candidates:
                    return self._fill(candidates, count, pool, base)

        if sector2:
            candidates = [q for q in pool if q.get('sector2') == sector2]
            if candidates:
                return self._fill(candidates, count, pool, base)

        if sector1:
            candidates = [q for q in pool if q.get('sector1') == sector1]
            if candidates:
                return self._fill(candidates, count, pool, base)

        if len(pool) >= count:
            return random.sample(pool, count)

        # Relax difficulty next, but keep the grade constraint.
        if len(base) >= count:
            return random.sample(base, count)

        return base
