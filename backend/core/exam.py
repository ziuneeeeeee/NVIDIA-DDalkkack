from .question_bank import QuestionBank

class MockExamGenerator:
    def __init__(self, qb: QuestionBank):
        self.qb = qb

    def generate(self, grade, topic_name=None, sector2=None, sector1=None):
        # 하3/중5/상2
        low_q = self.qb.search(grade=grade, topic_name=topic_name, sector2=sector2, sector1=sector1, difficulty=2, count=3)
        mid_q = self.qb.search(grade=grade, topic_name=topic_name, sector2=sector2, sector1=sector1, difficulty=3, count=5)
        high_q = self.qb.search(grade=grade, topic_name=topic_name, sector2=sector2, sector1=sector1, difficulty=4, count=2)
        
        return low_q + mid_q + high_q
