import os
import zipfile
import json
from pathlib import Path

def build_corpus():
    base_dir = Path(r"C:\Users\kdg68\Desktop\문제파일\3.개방데이터\1.데이터\Training\02.라벨링데이터")
    output_path = Path(r"C:\Users\kdg68\Desktop\sudal\backend\data\corpus_all_grades.json")
    
    questions = {}
    
    # Process question zips
    for zip_path in base_dir.glob("TL_1.문제_*.zip"):
        print(f"Processing {zip_path.name}")
        with zipfile.ZipFile(zip_path, 'r') as z:
            for filename in z.namelist():
                if filename.endswith(".json"):
                    try:
                        with z.open(filename) as f:
                            data = json.load(f)
                            q_id = data.get("id")
                            if q_id:
                                q_info = data.get("question_info", [{}])[0]
                                ocr_info = data.get("OCR_info", [{}])[0]
                                
                                questions[q_id] = {
                                    "id": q_id,
                                    "grade": q_info.get("question_grade"),
                                    "topic": q_info.get("question_topic"),
                                    "topic_name": q_info.get("question_topic_name"),
                                    "difficulty": q_info.get("question_difficulty"),
                                    "sector1": q_info.get("question_sector1"),
                                    "sector2": q_info.get("question_sector2"),
                                    "question_text": ocr_info.get("question_text", ""),
                                    "answer_text": "" # to be filled
                                }
                    except Exception as e:
                        print(f"Error reading {filename}: {e}")

    # Process answer zips
    for zip_path in base_dir.glob("TL_2.모범답안_*.zip"):
        print(f"Processing {zip_path.name}")
        with zipfile.ZipFile(zip_path, 'r') as z:
            for filename in z.namelist():
                if filename.endswith(".json"):
                    try:
                        with z.open(filename) as f:
                            data = json.load(f)
                            q_id = data.get("id")
                            if q_id and q_id in questions:
                                ans_info = data.get("answer_info", [{}])[0]
                                questions[q_id]["answer_text"] = ans_info.get("answer_text", "")
                    except Exception as e:
                        pass
                        
    # Write output
    print(f"Total questions loaded: {len(questions)}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(list(questions.values()), f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    build_corpus()
