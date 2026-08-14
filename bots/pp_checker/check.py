import json
import glob
import os

def check_all_maps():
    # 自動抓取目前目錄下所有符合 maps_*.json 的檔案
    json_files = glob.glob("maps_*.json")
    
    if not json_files:
        print("❌ 找不到任何 `maps_*.json` 檔案！請確認檔案命名與執行路徑是否正確。")
        return

    print(f"📋 開始檢查地圖庫，共發現 {len(json_files)} 個分類檔案：\n" + "-"*50)
    
    total_errors = 0

    for file_path in json_files:
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                maps = json.load(f)
            
            # 抓出所有的地圖 ID
            ids = [m['b'] for m in maps if 'b' in m]
            
            # 找出重複的 ID
            duplicates = set([x for x in ids if ids.count(x) > 1])
            
            if duplicates:
                print(f"❌ 檔案 [{file_name}] -> 發現重複的地圖 ID 喔！: {list(duplicates)}")
                total_errors += 1
            else:
                print(f"✅ 檔案 [{file_name}] -> 完美！內容無重複 ID (共 {len(ids)} 張圖)。")
                
        except json.JSONDecodeError:
            print(f"❌ 檔案 [{file_name}] -> 格式錯誤！JSON 語法有問題（可能少了逗號或括號）。")
            total_errors += 1
        except Exception as e:
            print(f"❌ 檔案 [{file_name}] -> 讀取時發生未知錯誤: {e}")
            total_errors += 1

    print("-"*50)
    if total_errors == 0:
        print("🎉 檢查完成！所有地圖庫檔案全部健康安全！")
    else:
        print(f"⚠️ 檢查完成，但發現有 {total_errors} 個檔案需要修正。")

if __name__ == "__main__":
    check_all_maps()