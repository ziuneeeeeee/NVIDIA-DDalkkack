class AdaptiveLearning:
    def __init__(self, alpha=0.3):
        self.alpha = alpha

    def update_mastery(self, current_mastery, is_correct):
        score = 1.0 if is_correct else 0.0
        new_mastery = (1 - self.alpha) * current_mastery + self.alpha * score
        return new_mastery

    def next_difficulty(self, current_difficulty, is_correct, streak=0):
        """난이도를 정답이면 올리고 오답이면 내린다.

        streak: 이번 문제 이전까지 이어진 연속 정답(+)/오답(-) 횟수. 같은 방향으로
        2회 이상 이어지고 있었다면 한 단계 더 크게 움직여 정체 구간을 빨리 벗어난다.
        """
        curr = int(current_difficulty) if current_difficulty else 3
        accelerate = (is_correct and streak >= 2) or (not is_correct and streak <= -2)
        step = 2 if accelerate else 1
        if is_correct:
            return min(5, curr + step)
        else:
            return max(1, curr - step)
