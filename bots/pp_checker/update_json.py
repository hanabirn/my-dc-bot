import os
import json
import glob
import time
from dotenv import load_dotenv
from ossapi import Ossapi

# 讀取環境變數取得 osu! API 憑證
load_dotenv()
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")

if not OSU_CLIENT_ID or not OSU_CLIENT_SECRET:
    print("❌ 錯誤：找不到 OSU_CLIENT_ID 或 OSU_CLIENT_SECRET。")
    exit()

api = Ossapi(int(OSU_CLIENT_ID), OSU_CLIENT_SECRET)

def fix_existing_json_files():
    """ 這是原本的功能：掃描並補全所有 JSON 檔案中缺少的歌名 """
    json_files = glob.glob("maps_*.json")
    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                maps_list = json.load(f)
            except Exception:
                continue

        has_changed = False
        for m in maps_list:
            if "b" in m and ("title" not in m or not m["title"]):
                print(f"   🔍 正在補全新加入的地圖 ID: {m['b']}...")
                try:
                    beatmap = api.beatmap(m['b'])
                    beatmapset = beatmap.beatmapset()
                    m["title"] = beatmapset.title
                    m["artist"] = beatmapset.artist
                    m["version"] = beatmap.version
                    has_changed = True
                    time.sleep(0.5)
                except Exception as e:
                    print(f"   ⚠️ 無法獲取 ID {m['b']} 的資訊: {e}")
        
        if has_changed:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(maps_list, f, ensure_ascii=False, indent=4)
            print(f"💾 {file_path} 已自動補全並存檔！")

def add_new_map_interactive():
    """ 新增功能：讓你可以直接在終端機輸入資料，自動抓歌名並分類存檔 """
    print("\n--- ✨ 快速新增農夫地圖工具 ---")
    try:
        b_id = int(input("請輸入 Beatmap ID (b): "))
        p_val = int(input("請輸入 預估 PP 值 (p): "))
        mod_val = input("請輸入 推薦 Mod (m) [預設 HDDT]: ").strip().upper() or "HDDT"
    except ValueError:
        print("❌ 輸入錯誤！ID 和 PP 必須是數字。")
        return

    # 自動計算該歸類到哪一個級距的檔案 (例如 245pp -> maps_200.json)
    level = (p_val // 100) * 100
    target_file = f"maps_{level}.json"

    print(f"📡 正在向官方 API 查詢地圖 {b_id} 的完整資訊...")
    try:
        beatmap = api.beatmap(b_id)
        beatmapset = beatmap.beatmapset()
        
        # 自動建立完整格式
        new_entry = {
            "s": beatmapset.id,
            "b": b_id,
            "p": p_val,
            "m": mod_val,
            "title": beatmapset.title,
            "artist": beatmapset.artist,
            "version": beatmap.version
        }
        
        # 讀取原本的檔案
        if os.path.exists(target_file):
            with open(target_file, "r", encoding="utf-8") as f:
                current_maps = json.load(f)
        else:
            current_maps = []
            
        # 檢查是否重複
        if any(m.get('b') == b_id for m in current_maps):
            print(f"⚠️ 地圖 ID {b_id} 其實已經存在於 {target_file} 裡囉，不用重複加！")
            return
            
        # 塞進清單並存檔
        current_maps.append(new_entry)
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(current_maps, f, ensure_ascii=False, indent=4)
            
        print(f"🎉 成功！已自動抓取《{beatmapset.title}》並寫入 `{target_file}`！")
        
    except Exception as e:
        print(f"❌ 查詢或寫入失敗，錯誤原因: {e}")

if __name__ == "__main__":
    # 1. 先跑原本的自動檢查/補全 (防呆用)
    fix_existing_json_files()
    
    # 2. 問你要不要新增地圖
    while True:
        choice = input("\n💡 是否要新增新的地圖到圖庫中？(y/n): ").strip().lower()
        if choice == 'y':
            add_new_map_interactive()
        else:
            print("👋 結束程式。別忘了用 git push 上傳到 Render 喔！")
            break