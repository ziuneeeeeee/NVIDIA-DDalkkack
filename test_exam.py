from core.exam import generate_mock_exam
import traceback
import sys
sys.stdout.reconfigure(encoding='utf-8')
try:
    problems = generate_mock_exam('python', 2)
    print(problems)
except Exception as e:
    traceback.print_exc()
